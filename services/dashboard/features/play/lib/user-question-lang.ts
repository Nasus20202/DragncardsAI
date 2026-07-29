import { UserQuestionPrompt } from "@/features/play/lib/play-session-events";

/**
 * Build the OpenUI Lang program that renders one `ask_user` question.
 *
 * WHY THIS TAKES NO STRINGS
 * =========================
 * OpenUI Lang is a language: `identifier = Component(arg, ...)`, where string
 * arguments are double-quoted with backslash escaping. Interpolating a
 * model-authored string into that source is therefore a code-injection sink in
 * exactly the way `dangerouslySetInnerHTML` is — a label containing `"` ends the
 * literal and the rest is parsed as further arguments. (Verified against
 * `@openuidev/lang-core` 0.2.10: `Text("with "quotes"")` parses as three
 * arguments, not one.)
 *
 * So no model-authored text is interpolated here at all. The program this
 * emits is built from two facts about the stored question — how many choices it
 * has, and whether it permits free text — and therefore consists of nothing but
 * component names, integers and punctuation drawn from this file. Every
 * presentation string is looked up at render time from the stored prompt, by
 * index, inside the component renderers in `user-question-library.tsx`.
 *
 * The consequence that matters: because a choice is addressed by its integer
 * index into the stored `choices` array and never by its value, no OpenUI Lang
 * program — whoever wrote it — can name a choice the stored row does not
 * contain. There is no syntax for it.
 */
export function buildUserQuestionLang(
  prompt: UserQuestionPrompt,
  options: { includeControls: boolean }
): string {
  const lines: string[] = [];
  const children: string[] = ["prompt"];

  if (options.includeControls) {
    if (prompt.choices.length > 0) {
      children.push("choices");
    }
    if (prompt.allowFreeText) {
      children.push("freetext");
    }
  }

  // `root` first: the library's own guidance is that the shell should parse
  // before its children, which is also what keeps a streamed program from
  // flickering.
  lines.push(`root = UserQuestion([${children.join(", ")}])`);
  lines.push("prompt = QuestionPrompt()");

  if (children.includes("choices")) {
    const refs = prompt.choices.map((_choice, index) => `choice${index}`);
    lines.push(`choices = ChoiceList([${refs.join(", ")}])`);
    for (const [index] of prompt.choices.entries()) {
      // The only variable that ever reaches the source text: an integer index.
      lines.push(`choice${index} = Choice(${index})`);
    }
  }

  if (children.includes("freetext")) {
    lines.push("freetext = FreeTextAnswer()");
  }

  return lines.join("\n") + "\n";
}
