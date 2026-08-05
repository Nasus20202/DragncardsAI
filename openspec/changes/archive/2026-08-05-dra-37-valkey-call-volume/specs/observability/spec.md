## ADDED Requirements

### Requirement: Span volume on a polling loop is reduced by issuing fewer commands, not by hiding spans

The requirement that a continuously polling loop be traced per batch of work rather than per polled iteration SHALL govern per-command dependency spans as well as application-level workflow spans.

A loop whose exported span count is dominated by idle iterations SHALL be regarded
as reporting a real defect in the loop, not as a telemetry defect, whenever the
instrumentation emits one span per underlying operation and therefore reports the
operation count faithfully.

Where a service's client emits one span per command and opens one connection per
command, a command, a connection and a span SHALL be treated as one quantity. The
remedy for too many such spans SHALL be to issue fewer commands — by batching, by
combining commands into a single round trip, or by lengthening a poll interval
that has no latency justification. Suppressing the tracer for a chatty path,
filtering the command span in the collector, or lowering the trace sample rate
SHALL NOT be used as the remedy while the underlying command count remains
disproportionate to the work performed, because each of those removes the only
signal that would reveal the cost while leaving the commands and the connections
in place.

Sampling and collector-side filtering remain legitimate once a path's command
count is proportionate to its work and the remaining span volume is a genuine
export-cost problem. That distinction SHALL be established by measurement — the
command count for a representative operation, compared against the span count for
the same operation — rather than asserted.

#### Scenario: A trace dominated by dependency spans from an idle loop is diagnosed as a loop defect

- **WHEN** a first-party service's trace is dominated by per-command dependency
  spans emitted by a loop that was idle
- **THEN** the command count for that loop SHALL be measured and compared against
  its span count, and where they match the loop SHALL be changed to issue fewer
  commands rather than to emit fewer spans

#### Scenario: A per-command span is not suppressed to reduce a trace's size

- **WHEN** a path emits one command span per Valkey command and its span volume is
  judged excessive
- **THEN** the tracer SHALL remain wired into that path, and the reduction SHALL
  come from the number of commands issued, so that the telemetry continues to
  report the service's real dependency load

#### Scenario: An interval with no latency justification is not set from an unrelated one

- **WHEN** a loop's poll or block interval controls only a fallback path, and a
  published event or an equivalent signal already ends the wait immediately
- **THEN** that interval SHALL be configured on its own terms and SHALL NOT be
  taken from a setting that governs an unrelated latency, so that its cost per
  second is a deliberate choice
