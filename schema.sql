create extension if not exists pgcrypto;

create table if not exists licenses (
  id uuid primary key default gen_random_uuid(),
  license_key text unique not null,
  buyer_email text not null,
  max_devices int not null default 1,
  status text not null default 'active', -- active|revoked
  ext_ref text unique,                   -- Paystack charge reference (for idempotency)
  created_at timestamptz default now()
);

create table if not exists activations (
  id uuid primary key default gen_random_uuid(),
  license_id uuid not null references licenses(id) on delete cascade,
  hwid text not null,
  created_at timestamptz default now(),
  unique (license_id, hwid)
);
