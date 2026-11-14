# ADR-0002: Mutagen CLI is source of truth

Status: accepted.

Mutagen owns synchronization, forwarding and session state. MutaUI invokes its installed CLI with argument lists, exact IDs, explicit working directories, timeouts and checked results. GUI polling never changes Mutagen watch frequency; no parallel engine or hidden agent is allowed.
