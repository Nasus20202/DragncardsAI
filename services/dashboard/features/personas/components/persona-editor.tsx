"use client";

import { Button, Card, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import {
  deletePersona,
  listAvailableSkills,
  listPersonas,
  listProviders,
  savePersona,
} from "@/features/play/lib/client-api";
import {
  MAX_PERSONA_PROMPT_CHARS,
  PersonaDraft,
  assemblePersonaRequest,
  buildDraftFromPersona,
  createEmptyPersonaDraft,
  describePersona,
  describePersonaDraftProblem,
  describePersonaDraftProblems,
  formatAllowedTools,
  parseAllowedTools,
} from "@/features/personas/lib/personas";
import { isWorking } from "@/features/play/lib/session-draft";
import {
  ComboSelectField,
  SelectField,
  SkillToggleList,
  SwitchField,
  TextInputField,
  TextareaField,
} from "@/features/shared/components/form-fields";
import {
  PersonaResponse,
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

const INHERIT_PROVIDER_VALUE = "";
const INHERIT_PROVIDER_LABEL = "Inherit from the spawning session";

/**
 * Authoring surface for agent personas: a reusable prompt, skill selection, and
 * tool configuration a subagent can be started from.
 *
 * Built from the shared field components the Play settings panel uses, so a new
 * surface renders the same controls rather than its own lookalikes.
 */
export function PersonaEditor() {
  const [personas, setPersonas] = useState<PersonaResponse[]>([]);
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [skills, setSkills] = useState<SkillDefinitionResponse[]>([]);
  const [draft, setDraft] = useState<PersonaDraft>(createEmptyPersonaDraft);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  /**
   * Whether the user has edited this draft, and whether a press of Save was
   * refused for it. Together they gate the validation messages: until one of
   * them holds, a fresh "New persona" form is not presented as already wrong,
   * and the summary beside the Save button appears only for a press that did
   * nothing, which is the moment the user needs telling why.
   */
  const [isDraftEdited, setIsDraftEdited] = useState(false);
  const [wasSaveRefused, setWasSaveRefused] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPersonas(await listPersonas());
      setErrorText(null);
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to load personas"
      );
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [personasResult, providersResult, skillsResult] =
        await Promise.allSettled([
          listPersonas(),
          listProviders(),
          listAvailableSkills(),
        ]);
      if (cancelled) {
        return;
      }
      if (personasResult.status === "fulfilled") {
        setPersonas(personasResult.value);
      } else {
        setErrorText(
          personasResult.reason instanceof Error
            ? personasResult.reason.message
            : "Failed to load personas"
        );
      }
      // Provider and skill catalogues are conveniences for the form; failing to
      // load them must not block authoring a prompt.
      if (providersResult.status === "fulfilled") {
        setProviders(providersResult.value);
      }
      if (skillsResult.status === "fulfilled") {
        setSkills(skillsResult.value);
      }
      setIsLoading(false);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function set<K extends keyof PersonaDraft>(key: K, value: PersonaDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setIsDraftEdited(true);
  }

  function startNew() {
    setDraft(createEmptyPersonaDraft());
    setEditingName(null);
    setStatusText("");
    setErrorText(null);
    setIsDraftEdited(false);
    setWasSaveRefused(false);
  }

  function startEditing(persona: PersonaResponse) {
    setDraft(buildDraftFromPersona(persona));
    setEditingName(persona.name);
    setStatusText("");
    setErrorText(null);
    setIsDraftEdited(false);
    setWasSaveRefused(false);
  }

  async function save() {
    const problem = describePersonaDraftProblem(draft);
    if (problem !== null) {
      // The button is deliberately pressable with an invalid draft, so this is
      // the guard that keeps one from reaching the orchestrator. The reason is
      // stated at the offending field and beside the button; `errorText` is
      // left for what the orchestrator says about a request we did make.
      setWasSaveRefused(true);
      return;
    }
    setWasSaveRefused(false);
    setIsBusy(true);
    setErrorText(null);
    setStatusText("Saving persona...");
    try {
      const saved = await savePersona(
        draft.name.trim(),
        assemblePersonaRequest(draft)
      );
      setEditingName(saved.name);
      setDraft(buildDraftFromPersona(saved));
      await refresh();
      setStatusText("Persona saved");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to save persona"
      );
      setStatusText("Save failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function remove(name: string) {
    setIsBusy(true);
    setErrorText(null);
    setStatusText("Deleting persona...");
    try {
      await deletePersona(name);
      if (editingName === name) {
        startNew();
      }
      await refresh();
      setStatusText("Persona deleted");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to delete persona"
      );
      setStatusText("Delete failed");
    } finally {
      setIsBusy(false);
    }
  }

  const providerItems = [
    { value: INHERIT_PROVIDER_VALUE, label: INHERIT_PROVIDER_LABEL },
    ...providers.map((provider) => {
      const usable = isWorking(provider);
      return {
        value: provider.provider_id,
        label: usable
          ? provider.provider_id
          : `${provider.provider_id} (no models)`,
        disabled: !usable,
      };
    }),
  ];
  const selectedProvider = providers.find(
    (provider) => provider.provider_id === draft.providerId
  );
  const modelItems = (selectedProvider?.models ?? []).map((model) => ({
    value: model,
    label: model,
  }));

  const promptLength = draft.systemPrompt.length;
  // Every problem is attributable to a field, so each is stated at its own
  // control. The same reason is repeated beside the Save button after a
  // refused press, because the fields are a scroll away from it on this form
  // and a press that appears to do nothing has to explain itself where it
  // happened.
  const problems = describePersonaDraftProblems(draft);
  const shownProblems =
    isDraftEdited || wasSaveRefused
      ? problems
      : { name: null, systemPrompt: null };
  const refusedSaveReason = wasSaveRefused
    ? describePersonaDraftProblem(draft)
    : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Agent personas</h1>
        <Button
          aria-label="New persona"
          isDisabled={isBusy}
          variant="ghost"
          onPress={startNew}
        >
          New persona
        </Button>
      </div>

      <p className="text-sm text-default-500">
        A persona is a reusable bundle of a detailed prompt, a skill selection,
        and a tool configuration. A subagent started from a persona captures it
        at that moment, so editing or deleting a persona never changes a
        subagent that is already running. A persona&apos;s tool allowlist can
        only narrow what a subagent may call — it can never grant access the
        session does not already have.
      </p>

      {errorText && <p className="text-sm text-danger">{errorText}</p>}
      {statusText && !errorText && (
        <p className="text-sm text-default-500">{statusText}</p>
      )}

      <Card className="p-4 shadow-none">
        <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
          Defined personas
        </p>
        {isLoading ? (
          <p className="pt-2 text-sm text-default-500">Loading personas...</p>
        ) : personas.length === 0 ? (
          <p
            className="pt-2 text-sm text-default-500"
            data-testid="personas-empty"
          >
            No personas are defined yet. Fill in the form below to create one.
          </p>
        ) : (
          <ul className="grid gap-2 pt-2" data-testid="personas-list">
            {personas.map((persona) => (
              <li
                key={persona.name}
                className="flex items-start justify-between gap-3 rounded-lg border border-default-200/60 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {persona.name}
                    {persona.display_name ? ` — ${persona.display_name}` : ""}
                  </p>
                  {persona.description && (
                    <p className="text-xs text-default-500">
                      {persona.description}
                    </p>
                  )}
                  <p className="text-[11px] text-default-400">
                    {describePersona(persona)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    aria-label={`Edit ${persona.name}`}
                    isDisabled={isBusy}
                    size="sm"
                    variant="ghost"
                    onPress={() => startEditing(persona)}
                  >
                    Edit
                  </Button>
                  <Button
                    aria-label={`Delete ${persona.name}`}
                    isDisabled={isBusy}
                    size="sm"
                    variant="ghost"
                    onPress={() => void remove(persona.name)}
                  >
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="grid gap-4 p-4 shadow-none">
        <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
          {editingName === null ? "New persona" : `Editing ${editingName}`}
        </p>

        <TextInputField
          id="persona-name"
          label="Name"
          placeholder="e.g. rules-lawyer"
          value={draft.name}
          disabled={editingName !== null}
          error={shownProblems.name ?? undefined}
          inputTestId="persona-name-input"
          onChange={(v) => set("name", v)}
        />
        <TextInputField
          id="persona-display-name"
          label="Display name"
          placeholder="e.g. Rules Lawyer"
          value={draft.displayName}
          onChange={(v) => set("displayName", v)}
        />
        <TextareaField
          id="persona-description"
          label="Description"
          description="Shown to the orchestrating agent so it can pick this persona."
          rows={2}
          value={draft.description}
          onChange={(v) => set("description", v)}
        />

        <Separator />

        <TextareaField
          id="persona-prompt"
          label="System prompt"
          description={`${promptLength} / ${MAX_PERSONA_PROMPT_CHARS} characters`}
          error={shownProblems.systemPrompt ?? undefined}
          rows={10}
          value={draft.systemPrompt}
          inputTestId="persona-prompt-input"
          onChange={(v) => set("systemPrompt", v)}
        />

        <Separator />

        <SelectField
          id="persona-provider"
          label="Provider"
          items={providerItems}
          value={draft.providerId}
          onChange={(v) => set("providerId", v)}
        />
        <ComboSelectField
          id="persona-model"
          label="Model"
          items={modelItems}
          value={draft.modelName}
          disabled={modelItems.length === 0}
          onChange={(v) => set("modelName", v)}
        />

        <Separator />

        <SwitchField
          id="persona-reasoning"
          label="Reasoning"
          description="Ask the provider for a reasoning stream for this persona."
          checked={draft.reasoningEnabled}
          onChange={(v) => set("reasoningEnabled", v)}
        />
        {draft.reasoningEnabled && (
          <>
            <SelectField
              id="persona-effort"
              label="Reasoning effort"
              items={[
                { value: "low", label: "Low" },
                { value: "medium", label: "Medium" },
                { value: "high", label: "High" },
              ]}
              value={draft.reasoningEffort}
              onChange={(v) =>
                set("reasoningEffort", v as "low" | "medium" | "high")
              }
            />
            <TextInputField
              id="persona-reasoning-tokens"
              label="Reasoning max tokens"
              placeholder="e.g. 4096"
              value={draft.reasoningMaxTokens}
              onChange={(v) => set("reasoningMaxTokens", v)}
            />
          </>
        )}

        <Separator />

        <SwitchField
          id="persona-override-skills"
          label="Choose this persona's skills"
          description="Off inherits the skills of whichever session spawns the subagent."
          checked={draft.selectedSkills !== null}
          onChange={(v) => set("selectedSkills", v ? [] : null)}
        />
        {draft.selectedSkills !== null && (
          <SkillToggleList
            skills={skills}
            selectedSkills={draft.selectedSkills}
            testId="persona-skills"
            skillTestId={(name) => `persona-skill-${name}`}
            onChange={(next) => set("selectedSkills", next)}
          />
        )}

        <Separator />

        <SwitchField
          id="persona-narrow-tools"
          label="Narrow this persona's tools"
          description="Off gives the subagent every tool its session exposes. On, only the tools listed below survive — a persona can narrow tool access, never widen it."
          checked={draft.allowedTools !== null}
          onChange={(v) => set("allowedTools", v ? [] : null)}
        />
        {draft.allowedTools !== null && (
          <TextareaField
            id="persona-allowed-tools"
            label="Allowed tools"
            description="One tool name per line. A name the session does not expose simply has no effect."
            rows={4}
            value={formatAllowedTools(draft.allowedTools)}
            inputTestId="persona-allowed-tools-input"
            onChange={(v) => set("allowedTools", parseAllowedTools(v))}
          />
        )}

        <div className="flex items-center justify-end gap-3">
          {refusedSaveReason !== null && (
            <p
              className="text-xs text-danger"
              id="persona-save-problem"
              role="alert"
              data-testid="persona-save-problem"
            >
              {refusedSaveReason}
            </p>
          )}
          <Button
            aria-label="Save persona"
            aria-describedby={
              refusedSaveReason !== null ? "persona-save-problem" : undefined
            }
            isDisabled={isBusy}
            variant="primary"
            onPress={() => void save()}
          >
            Save persona
          </Button>
        </div>
      </Card>
    </div>
  );
}
