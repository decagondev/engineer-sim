# Current system

The docs product is request/response. Presence today is a last_seen timestamp
that goes stale when laptops sleep. A hack on one box kept sockets for an
internal pilot; it does not survive deploys.

Friend/workspace membership lives in Postgres. There is no room directory.
CDN in front of the web app; APIs are not edge-terminated for websockets.
