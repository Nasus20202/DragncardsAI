import "@testing-library/jest-dom";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The question card is the only Hero UI surface the transcript renders, so it is
 * mocked here the way the other Play tests mock Hero UI: the real `Button` is a
 * react-aria press target that does not answer a plain `click`.
 */
type MockChildrenProps = { children?: React.ReactNode };

vi.mock("@heroui/react", () => ({
  Button: ({
    children,
    onPress,
    isDisabled,
    "data-testid": dataTestId,
  }: MockChildrenProps & {
    onPress?: () => void;
    isDisabled?: boolean;
    "data-testid"?: string;
  }) => (
    <button
      data-testid={dataTestId}
      disabled={isDisabled}
      type="button"
      onClick={onPress}
    >
      {children}
    </button>
  ),
  TextField: ({
    children,
    isDisabled,
  }: MockChildrenProps & { isDisabled?: boolean }) => (
    <div data-disabled={isDisabled ? "true" : "false"}>{children}</div>
  ),
  Input: ({
    value,
    placeholder,
    onChange,
    "data-testid": dataTestId,
  }: {
    value?: string;
    placeholder?: string;
    onChange?: React.ChangeEventHandler<HTMLInputElement>;
    "data-testid"?: string;
  }) => (
    <input
      data-testid={dataTestId}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
    />
  ),
}));

const { PlayTranscript } =
  await import("@/features/play/components/play-transcript");
const { STREAM_EVENT_TYPES } =
  await import("@/features/play/lib/play-session-events");

import {
  JobDetail,
  JobEventResponse,
  SessionDetail,
  UserQuestionAnswerRequest,
} from "@/features/shared/lib/types";

type AnswerFn = (
  jobId: string,
  questionId: string,
  body: UserQuestionAnswerRequest
) => Promise<void>;

const QUESTION_ID = "11111111-2222-3333-4444-555555555555";

const selectedSession: SessionDetail = {
  id: "session-1",
  name: "Session",
  status: "active",
  context_recent_message_limit: null,
  context_recent_tool_exchange_limit: null,
  metadata: {},
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  terminated_at: null,
  model_config: null,
  skills: [],
  mcps: [],
  recent_job: null,
  recent_jobs: [],
};

function questionEvent(
  overrides: Partial<{
    choices: unknown[];
    allow_free_text: boolean;
    question: string;
  }> = {}
): JobEventResponse {
  return {
    id: "e1",
    event_type: "user_question",
    payload: {
      question_id: QUESTION_ID,
      question: "Which hero should I play?",
      choices: [
        { label: "Spider-Man", value: "spider-man" },
        {
          label: "She-Hulk",
          value: "she-hulk",
          description: "Bigger hand size",
        },
      ],
      allow_free_text: false,
      ...overrides,
    } as JobEventResponse["payload"],
    created_at: "2026-05-11T00:00:01Z",
  };
}

function makeJob(events: JobEventResponse[], status = "running"): JobDetail {
  return {
    id: "job-1",
    prompt: "Play a turn",
    metadata: {},
    status,
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: "2026-05-11T00:00:00Z",
    started_at: "2026-05-11T00:00:01Z",
    completed_at: null,
    latest_event_id: events.at(-1)?.id ?? null,
    latest_event_type: events.at(-1)?.event_type ?? null,
    outputs: [],
    events,
    available_tools: [],
  };
}

function renderTranscript(job: JobDetail, onAnswerQuestion?: AnswerFn) {
  return render(
    <PlayTranscript
      jobs={[job]}
      streamingJobId={job.status === "running" ? job.id : null}
      selectedSession={selectedSession}
      streamState="idle"
      statusText="Ready"
      isBusy={false}
      errorText={null}
      onOpenSettings={vi.fn()}
      onAnswerQuestion={onAnswerQuestion}
      settingsOpen={false}
    />
  );
}

describe("user_question in the transcript", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollTo = vi.fn();
  });

  it("subscribes to the three question event types on the SSE stream", () => {
    // Without these the EventSource silently drops them: use-job-streaming
    // registers one named listener per entry and has no onmessage fallback.
    expect(STREAM_EVENT_TYPES).toContain("user_question");
    expect(STREAM_EVENT_TYPES).toContain("user_question_answered");
    expect(STREAM_EVENT_TYPES).toContain("user_question_closed");
  });

  it("renders one button per choice and answers with that choice value", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    renderTranscript(makeJob([questionEvent()]), onAnswer);

    expect(screen.getByTestId("user-question-text")).toHaveTextContent(
      "Which hero should I play?"
    );
    expect(screen.getByTestId("user-question-choices").children).toHaveLength(
      2
    );
    expect(screen.getByTestId("user-question-choice-1")).toHaveTextContent(
      "Bigger hand size"
    );
    // Free text is offered only when the model allowed it.
    expect(screen.queryByTestId("user-question-free-text")).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByTestId("user-question-choice-0"));
    });

    expect(onAnswer).toHaveBeenCalledTimes(1);
    expect(onAnswer).toHaveBeenCalledWith("job-1", QUESTION_ID, {
      choice_value: "spider-man",
    });
  });

  it("submits the free-text answer when the model allowed one", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    renderTranscript(
      makeJob([questionEvent({ choices: [], allow_free_text: true })]),
      onAnswer
    );

    fireEvent.change(screen.getByTestId("user-question-free-text"), {
      target: { value: "  Ms. Marvel  " },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("user-question-free-text-submit"));
    });

    expect(onAnswer).toHaveBeenCalledWith("job-1", QUESTION_ID, {
      text: "Ms. Marvel",
    });
  });

  it("shows the recorded answer and no buttons after a reload", () => {
    // A fresh mount over the durable event list — exactly what a page reload
    // produces once the orchestrator replays `job_events` from after=0.
    const onAnswer = vi.fn();
    renderTranscript(
      makeJob(
        [
          questionEvent(),
          {
            id: "e2",
            event_type: "user_question_answered",
            payload: {
              question_id: QUESTION_ID,
              source: "choice",
              value: "spider-man",
              label: "Spider-Man",
              text: null,
            },
            created_at: "2026-05-11T00:00:02Z",
          },
        ],
        "completed"
      ),
      onAnswer
    );

    expect(screen.getByTestId("user-question-answer")).toHaveTextContent(
      "Answered: Spider-Man"
    );
    expect(screen.queryByTestId("user-question-choices")).toBeNull();
    expect(screen.queryByTestId("user-question-choice-0")).toBeNull();
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("renders the closed state with no buttons, distinguishing the reason", () => {
    renderTranscript(
      makeJob([
        questionEvent(),
        {
          id: "e2",
          event_type: "user_question_closed",
          payload: {
            question_id: QUESTION_ID,
            reason: "timeout",
            waited_seconds: 600,
          },
          created_at: "2026-05-11T00:00:02Z",
        },
      ]),
      vi.fn()
    );

    expect(screen.getByTestId("user-question-closed")).toHaveTextContent(
      /timed out/i
    );
    expect(screen.queryByTestId("user-question-choice-0")).toBeNull();
  });

  it("disables the controls when the job is already terminal", () => {
    renderTranscript(makeJob([questionEvent()], "failed"), vi.fn());

    expect(screen.getByTestId("user-question-choice-0")).toBeDisabled();
    expect(screen.getByTestId("user-question-unanswerable")).toHaveTextContent(
      /can no longer be answered/i
    );
  });

  it("sends one request for a double click and stays disabled on a 409", async () => {
    let rejectAnswer: (error: Error) => void = () => {};
    const onAnswer = vi.fn(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectAnswer = reject;
        })
    );
    renderTranscript(makeJob([questionEvent()]), onAnswer);

    const first = screen.getByTestId("user-question-choice-0");
    fireEvent.click(first);
    // A second click while the first submit is still in flight must not answer
    // twice.
    fireEvent.click(first);
    fireEvent.click(screen.getByTestId("user-question-choice-1"));
    expect(onAnswer).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("user-question-choice-0")).toBeDisabled();

    await act(async () => {
      rejectAnswer(
        new Error("Question 1111 is no longer awaiting an answer (answered).")
      );
    });

    expect(screen.getByTestId("user-question-error")).toHaveTextContent(
      "Question 1111 is no longer awaiting an answer (answered)."
    );
    expect(screen.getByTestId("user-question-choice-0")).toBeDisabled();
    expect(screen.getByTestId("user-question-choice-1")).toBeDisabled();

    // No retry: the answer may well have landed server-side.
    fireEvent.click(screen.getByTestId("user-question-choice-0"));
    expect(onAnswer).toHaveBeenCalledTimes(1);
  });

  it("renders model-authored text literally, never as markup", () => {
    const injected = "<img src=x onerror=alert(1)>";
    renderTranscript(
      makeJob([
        questionEvent({
          question: `Pick one <script>alert("q")</script>`,
          choices: [
            { label: injected, value: injected, description: injected },
          ],
        }),
      ]),
      vi.fn()
    );

    expect(screen.getByTestId("user-question-choice-0")).toHaveTextContent(
      injected
    );
    expect(screen.getByTestId("user-question-text")).toHaveTextContent(
      'Pick one <script>alert("q")</script>'
    );
    // The strings never become elements — they are escaped text nodes.
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(document.body.innerHTML).toContain("&lt;img");
    expect(document.body.innerHTML).toContain("&lt;script&gt;");
  });
});
