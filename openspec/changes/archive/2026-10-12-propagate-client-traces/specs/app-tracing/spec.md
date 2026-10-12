# Spec Delta

## ADDED Requirements

### Requirement: Requests continue the caller's trace
When an incoming request carries a valid W3C `traceparent` header, the API SHALL make its SERVER span a child of the span named in it, in the same trace, and SHALL record the request's spans when that parent is sampled. A request without the header SHALL start a new trace.

#### Scenario: Client sends traceparent
- **WHEN** a client posts a message with `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **THEN** the SERVER span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and the agent spans of that turn share the trace id

#### Scenario: No traceparent
- **WHEN** a client posts a message without a `traceparent` header
- **THEN** the SERVER span is the root of a new trace
