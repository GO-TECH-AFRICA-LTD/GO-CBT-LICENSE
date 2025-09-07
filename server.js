import express from "express";
import crypto from "crypto";
import jwt from "jsonwebtoken";
import pg from "pg";
import bodyParser from "body-parser";

const app = express();

// RAW body only for webhook (signature needs raw bytes)
app.use("/paystack/webhook", bodyParser.raw({ type: "*/*" }));
// Normal JSON for all other routes
app.use(express.json());

// ==== ENV ====
const { Pool } = pg;
const db = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

const PAYSTACK_SECRET = process.env.PAYSTACK_SECRET; // sk_test_... or sk_live_...
const JWT_PRIVATE = process.env.JWT_PRIVATE;         // RS256 private key (PEM)
const JWT_PUBLIC  = process.env.JWT_PUBLIC;          // RS256 public key  (PEM)
const TOKEN_DAYS  = parseInt(process.env.TOKEN_DAYS || "30", 10);

// ==== helpers ====
function randomKey() {
  // Human-friendly license key
  return "GOCBT-" + crypto.randomBytes(12).toString("base64url").toUpperCase();
}
function signToken(payload) {
  return jwt.sign(payload, JWT_PRIVATE, { algorithm: "RS256", expiresIn: `${TOKEN_DAYS}d` });
}

// Healthcheck
app.get("/", (_, res) => res.send("GO CBT License server up"));

// 1) PAYSTACK WEBHOOK -> create/issue license on charge.success
app.post("/paystack/webhook", async (req, res) => {
  try {
    const sig = req.headers["x-paystack-signature"];
    const computed = crypto.createHmac("sha512", PAYSTACK_SECRET).update(req.body).digest("hex");
    if (sig !== computed) return res.sendStatus(401);

    const evt = JSON.parse(req.body.toString("utf8"));
    if (evt?.event !== "charge.success") return res.sendStatus(200);

    const email = evt?.data?.customer?.email;
    const reference = evt?.data?.reference; // Paystack ref; unique per successful charge
    if (!email || !reference) return res.sendStatus(200);

    await db.query("BEGIN");

    // idempotency: if we already issued for this reference, do nothing
    const exists = await db.query("select id from licenses where ext_ref=$1", [reference]);
    let licenseKey = randomKey();
    if (exists.rowCount === 0) {
      // Issue license
      await db.query(
        `insert into licenses (license_key, buyer_email, max_devices, status, ext_ref)
         values ($1, $2, $3, 'active', $4)`,
        [licenseKey, email, 1, reference]
      );
    } else {
      // already exists -> fetch the key so we can resend if needed
      const r = await db.query("select license_key from licenses where ext_ref=$1", [reference]);
      licenseKey = r.rows[0].license_key;
    }

    await db.query("COMMIT");

    // TODO: email the license to buyer (Resend/SES/Mailgun). For now we just log:
    console.log("Issued license", licenseKey, "to", email, "for reference", reference);

    return res.sendStatus(200);
  } catch (err) {
    console.error(err);
    try { await db.query("ROLLBACK"); } catch {}
    return res.sendStatus(500);
  }
});

// 2) ACTIVATE -> returns JWT if license ok and seat available
app.post("/activate", async (req, res) => {
  const { email, license_key, hwid } = req.body || {};
  if (!email || !license_key || !hwid) return res.status(400).json({ ok: false, msg: "missing fields" });

  const L = await db.query("select * from licenses where license_key=$1 and status='active'", [license_key]);
  if (!L.rowCount) return res.status(400).json({ ok: false, msg: "invalid license" });

  const lic = L.rows[0];
  // Optional: enforce email match (comment this out if you allow any email)
  if (email.toLowerCase() !== lic.buyer_email.toLowerCase()) {
    return res.status(400).json({ ok: false, msg: "email mismatch" });
  }

  // Enforce device limit
  const C = await db.query("select count(*)::int as c from activations where license_id=$1", [lic.id]);
  if (C.rows[0].c >= lic.max_devices) {
    // allow re-activation on same hwid without counting a new seat
    const same = await db.query("select 1 from activations where license_id=$1 and hwid=$2", [lic.id, hwid]);
    if (!same.rowCount) return res.status(403).json({ ok: false, msg: "device limit reached" });
  } else {
    await db.query(
      "insert into activations (license_id, hwid) values ($1, $2) on conflict (license_id, hwid) do nothing",
      [lic.id, hwid]
    );
  }

  const token = signToken({ license_id: lic.id, license_key, email, hwid });
  return res.json({ ok: true, token, max_devices: lic.max_devices });
});

// 3) VERIFY -> validate token + refresh (sliding window)
app.post("/verify", async (req, res) => {
  const { token, hwid } = req.body || {};
  try {
    const payload = jwt.verify(token, JWT_PUBLIC, { algorithms: ["RS256"] });
    if (payload.hwid !== hwid) return res.status(400).json({ ok: false, msg: "hwid mismatch" });

    const S = await db.query("select status from licenses where id=$1", [payload.license_id]);
    if (!S.rowCount || S.rows[0].status !== "active") return res.status(403).json({ ok: false, msg: "revoked" });

    const newToken = signToken({ license_id: payload.license_id, license_key: payload.license_key, email: payload.email, hwid });
    return res.json({ ok: true, token: newToken });
  } catch (e) {
    return res.status(401).json({ ok: false, msg: "invalid token" });
  }
});

// 4) DEACTIVATE -> free a seat for this hwid
app.post("/deactivate", async (req, res) => {
  const { token, hwid } = req.body || {};
  try {
    const payload = jwt.verify(token, JWT_PUBLIC, { algorithms: ["RS256"] });
    await db.query("delete from activations where license_id=$1 and hwid=$2", [payload.license_id, hwid]);
    return res.json({ ok: true });
  } catch {
    return res.status(401).json({ ok: false });
  }
});

app.listen(process.env.PORT || 3000, () => console.log("License server running"));
