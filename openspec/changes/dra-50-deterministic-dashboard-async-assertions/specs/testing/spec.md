## ADDED Requirements

### Requirement: Frontend tests wait for the render they assert on
A frontend test SHALL assert on content that appears as the result of an
asynchronous chain only through a query that waits for it — `findBy*`, or a
synchronous query inside `waitFor` — and SHALL NOT query for it synchronously
after awaiting some earlier step of that chain.

Awaiting that a mocked API function was *called* SHALL NOT be treated as
evidence that the render caused by its result has committed. A call is the first
step of the handler that makes it; the state updates that follow it are separated
from it by every remaining `await` in that handler plus a React commit.

The suite SHALL NOT rely on React Testing Library's post-`waitFor` drain to
deliver those commits. That drain is a single `setTimeout(…, 0)`, clamped to one
millisecond — a fixed grace period rather than a wait for the condition. Whether a
handler's promise chain fits inside it depends on how busy the machine is, which
makes any assertion resting on it a function of the machine rather than of the
behaviour under test.

A synchronous query MAY follow an awaited one when it reads state committed in the
same render as the awaited content — state set together with it in one handler is
batched into one commit and is therefore already on screen.

#### Scenario: Content rendered after an awaited API call is awaited
- **WHEN** a test submits a prompt and asserts on the streaming banner that
  appears once the submission's follow-up request has resolved and streaming has
  started
- **THEN** the banner SHALL be asserted through an awaited query, so the
  assertion waits for the render that produces it rather than for the submission
  call that precedes it

#### Scenario: The result does not depend on the machine's load
- **WHEN** the dashboard suite is run repeatedly while other test suites are
  running on the same machine, so that promise chains and timers are stretched
- **THEN** every test SHALL produce the same result as it does on an idle
  machine, and no test SHALL fail because a render had not committed when it was
  queried

#### Scenario: State committed alongside awaited content stays synchronous
- **WHEN** a test has awaited content whose render also set other state in the
  same handler
- **THEN** that other state MAY be asserted synchronously, because React commits
  the batched updates together and the awaited query has already waited for that
  commit
