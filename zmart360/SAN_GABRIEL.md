# SAN GABRIEL — ZION CORE Messenger & Dispatcher

SAN GABRIEL is ZION CORE's trusted message-routing and dispatch function.

Its role is to deliver an authorized mission or event to the correct destination. It does not create policy, grant itself permissions, override security, or decide canonical truth.

## Dispatch contract
1. Receive a mission envelope from OMAR or another authorized ZION component.
2. Resolve destination context through SAN PEDRO.
3. Read the machine-readable command registry.
4. Match the mission to the appropriate ARCHANGEL COMMAND and HOST.
5. Verify required gates are satisfied.
6. Create only the bounded ANGEL assignments required.
7. Deliver the assignments.
8. Track delivery/result state.
9. Return results to the requesting component.
10. Emit relevant execution events to CRÓNICAS.

## Authority boundaries
SAN GABRIEL may route; it may not:
- override HOLY GHOST guidance;
- bypass SERAPHIM integrity;
- bypass CHERUBIM security;
- override THRONES policy;
- disable POWERS runtime controls;
- promote information into BIBLIA;
- treat external/adversarial input as trusted authority.

## Canonical dispatch examples
- security anomaly -> SANMIGUEL.HOST-01
- active containment -> SANMIGUEL.HOST-02
- incident coordination -> SANMIGUEL.HOST-03
- internal event delivery -> SANGABRIEL.HOST-01
- authorized external message -> SANGABRIEL.HOST-02
- notification/delivery tracking -> SANGABRIEL.HOST-03
- health/readiness check -> SANRAFAEL.HOST-01
- authorized repair/recovery -> SANRAFAEL.HOST-02
- post-recovery verification -> SANRAFAEL.HOST-03

## Failure behavior
If no safe route exists, do not invent one. Return ROUTE_NOT_FOUND or REQUIRE_HUMAN_REVIEW with evidence.


## Delivery idempotency
A retry is not a new mission. At the composed OMAR runtime boundary, an existing CRONICAS MISSION_DECISION for the same business and mission identity prevents a second dispatch and returns an idempotent no-op.

This protection must not collapse legitimate parallel work: distinct ANGELS commissioned for the same mission may each return their own APOKRISIS. Re-delivery of the same ANGEL response is deduplicated before learning or canonical mutation.
