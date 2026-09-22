# CLAUDE.md

Project instructions for Claude Code, and a plain account of how this repo was
built with it. Both audiences matter: the tool reads the rules, a human reads
the rest.

## Conventions the tool must keep

- **SQL models are plain SELECTs.** `sql/staging/NN_name.sql` becomes
  `staging.name` (view); `sql/marts/NN_name.sql` becomes `marts.name` (table);
  `sql/macros/*.sql` runs verbatim. The numeric prefix is execution order and
  is stripped from the object name. `src/mdw/build.py` is the only place that
  knows this.
- **Every mart change ships with a quality assertion** in `tests/quality/`.
  An assertion is a query that returns violating rows; zero rows passes.
- **`tests/` is offline.** The pipeline test drives a synthetic companyfacts
  document through raw -> staging -> marts -> quality. Never add a test that
  calls sec.gov; CI has no network policy and no User-Agent.
- **Never key facts on `fy`/`fp`.** Those describe the filing, not the period.
  Key on `period_start`/`period_end`. See `sql/staging/02_stg_company_facts.sql`.
- **No secrets, no contact details, no data in git.** `EDGAR_USER_AGENT` is
  read from the environment and deliberately has no default. `data/` is
  ignored and fully reproducible.
- Keep the dependency list at `duckdb` + `requests`. If a change needs pandas,
  it is probably a SQL change in disguise.

## How this was built

This repository was built in a single Claude Code session, with the human
making the calls that matter and the model doing the typing and the first
draft of most reasoning. Roughly:

1. **Human decisions first.** Purpose (a recruiter-facing demonstration of SQL
   and Python financial data engineering), data source (SEC EDGAR companyfacts
   over FRED or synthetic data, because EDGAR is genuinely messy), scope (one
   focused repo rather than a research monorepo), and the hard rule that this
   codebase shares nothing with any other project.
2. **Discovery before design.** A throwaway script pulled one company's facts
   and printed a sample. That sample, a FY2016 revenue figure filed in 2018,
   set the design: the warehouse is organised around fact *revisions* and
   point-in-time correctness, not around "the latest number".
3. **Layered build.** Client -> ingest -> model runner -> SQL models -> quality
   assertions -> offline tests -> CI, each written and syntax-checked before the
   next. The SQL was drafted by the model and reviewed line by line by the
   human against the EDGAR documentation.
4. **Tested against reality.** The offline suite passed first; the live run
   against eight filers then surfaced the things fixtures never do (SEC's
   User-Agent gate returning 403, revenue tag drift across filers), and those
   became code and comments.

What the model did not do: choose the data source, decide what to publish,
or decide what "correct" means for a restated number. Those are documented in
`README.md` under *Design notes*.
