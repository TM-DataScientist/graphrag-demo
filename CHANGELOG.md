# Change Log

## 2026-04-09

- Executed the GraphRAG local query for `Who is Scrooge and what are his main relationships?` against `ragtest`.
- Used the current CLI entrypoint (`python -m graphrag query` / `graphrag query`) because `python -m graphrag.query` is not directly executable in `graphrag==3.0.8`.
- Re-ran the query with UTF-8 output enabled to avoid a Windows `cp932` console encoding error while printing the response.
