# Official deployment references

Checked 2026-11-05. Library and cloud behavior can change; re-check when upgrading.

- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm): eligible home-region resources, current A1 quotas, capacity and idle-resource reclamation. Free cost is conditional on the tenancy's limits and selected services.
- [Oracle Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm): trial versus ongoing free resources and account constraints.
- [systemd.timer](https://freedesktop.org/software/systemd/man/latest/systemd.timer.html): `OnCalendar`, persistent catch-up and timer accuracy. The supplied timer deliberately schedules after each candle closes.
- [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment): `run_every` refreshes the dashboard fragment independently of the execution process.
- [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication): identity and authorization are separate concerns. This application uses its local FastAPI/Argon2 login and backend control authorization rather than requiring an external OIDC provider.
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https): public DNS, port and certificate prerequisites. The Caddy template requires an actual configured hostname.
- [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy): Streamlit WebSocket proxying and HTTP transport behavior.
- [SQLite WAL](https://sqlite.org/wal.html): simultaneous local readers/writer, one-host shared-memory requirement and WAL backup considerations.
- [SQLite online backup API](https://sqlite.org/backup.html): consistent database snapshots. Cross-database consistency additionally requires stopping application writers.

The design decisions in ARCHITECTURE.md are engineering choices for this application; these references establish documented platform behavior, not the profitability or reliability of a deployed strategy.
