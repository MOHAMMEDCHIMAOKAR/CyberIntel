create table if not exists public.sources (
  id text primary key,
  name text not null,
  feed_url text not null,
  homepage_url text not null,
  description text,
  enabled boolean not null default true,
  last_fetched_at timestamptz
);

create table if not exists public.articles (
  id text primary key,
  source_id text not null references public.sources(id) on update cascade on delete restrict,
  source text not null,
  title text not null,
  summary text not null default '',
  url text not null,
  published_at timestamptz not null,
  category text not null,
  tags jsonb not null default '[]'::jsonb,
  image text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists articles_published_at_idx on public.articles (published_at desc);
create index if not exists articles_source_id_idx on public.articles (source_id);
create index if not exists articles_category_idx on public.articles (category);

alter table public.sources enable row level security;
alter table public.articles enable row level security;

revoke all on table public.sources from anon, authenticated;
revoke all on table public.articles from anon, authenticated;
grant all on table public.sources to service_role;
grant all on table public.articles to service_role;
