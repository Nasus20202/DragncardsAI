## ADDED Requirements

### Requirement: A failed RESP command is attributed to the call that failed
The shared RESP client SHALL NOT await the connection's close waiter while unwinding
from a failed command.

asyncio stores a single exception instance on a transport's protocol and hands that
same object to both the `StreamReader` and the connection's close waiter. Awaiting the
close waiter during unwinding therefore raises the exception that is already
propagating. Even when that second raise is caught and discarded, raising it appends
the close-time frames to the exception object's traceback, and the original exception
then escapes carrying a traceback that ends at the cleanup line instead of the call
that failed. That misattribution is what made a dead connection read as a cosmetic
close error in DRA-35.

The client SHALL still close the writer on every exit path, so no socket is leaked;
only the *await* is skipped, and only when the command has already failed.

A command that received a complete reply SHALL still await the close waiter, and that
await SHALL remain guarded, because a reset can legitimately arrive after a valid reply
and must not fail a command whose result is already in hand.

#### Scenario: A mid-command reset blames the read
- **WHEN** the peer resets the connection before sending a reply
- **THEN** `execute` SHALL raise the connection error with a traceback naming the RESP read, and that traceback SHALL NOT contain the close-waiter frames

#### Scenario: A reset after a complete reply is not an error
- **WHEN** the peer sends a complete reply and then resets the connection abortively
- **THEN** `execute` SHALL return the parsed reply and SHALL NOT raise

#### Scenario: The writer is closed on every path
- **WHEN** a command fails for any reason
- **THEN** the client SHALL still call `close()` on the writer before propagating
