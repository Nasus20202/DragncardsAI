## ADDED Requirements

### Requirement: The question surface renders through a model-facing UI language
The dashboard SHALL render the surface for a question from the agent through a
generative-UI runtime — a component library with typed props, and a renderer that
resolves a program written in that runtime's language against it — rather than by
hand-assembling the surface in React.

The component library SHALL be built from the dashboard's own components, so the
question surface keeps the transcript's existing visual language. The runtime's own
component library SHALL NOT be installed, because it would apply its own theme to
the app and would place a markdown renderer in the path of model-authored text. No
stylesheet belonging to the runtime SHALL be loaded.

The library SHALL be a closed registry: a program naming a component the library
does not define SHALL render nothing. There SHALL be no component that renders
markup supplied as text.

Adopting the runtime SHALL NOT require an API key or a network endpoint belonging
to its vendor, and no part of the render path SHALL send the question, the answer,
or any other content to a third party.

#### Scenario: The surface renders from a program
- **WHEN** a question awaiting an answer is rendered
- **THEN** the surface SHALL be produced by resolving a program in the runtime's
  language against the dashboard's component library
- **AND** it SHALL show the question text and one control per offered choice, as
  before

#### Scenario: A component the library does not define renders nothing
- **WHEN** a program names a component absent from the library
- **THEN** nothing SHALL be rendered for that component
- **AND** no element described by its arguments SHALL exist in the rendered output

#### Scenario: No vendor stylesheet is loaded
- **WHEN** the dashboard renders a question surface
- **THEN** no stylesheet belonging to the generative-UI runtime SHALL be present in
  the document

### Requirement: No model-authored text is interpolated into a program
The dashboard SHALL build the program for a question from that question's *shape*
only — how many choices it offers, and whether it permits a free-text answer. The
program SHALL NOT contain the question text, a choice's label, a choice's value, or
a choice's description. Every such string SHALL be looked up when the surface
renders, from the stored question, by the component that displays it.

This is required because the language a question surface is described in has string
literals, so interpolating a model-authored string into a program is a
code-injection sink: a label containing the literal's delimiter ends it, and the
remainder is parsed as code.

#### Scenario: The program carries no model-authored text
- **WHEN** a program is built for a question whose text and choice labels contain
  the language's string delimiter and statements of its own
- **THEN** the program SHALL NOT contain any of those strings
- **AND** the surface SHALL still display them as text when it renders

### Requirement: A program identifies a choice by position, not by value
A component representing an offered choice SHALL take that choice's position in the
stored choice list and SHALL NOT take its label, its value, or its description. The
label and description displayed, and the value submitted, SHALL all be read from
the stored question at that position.

A program MAY therefore reorder or omit choices, which is presentation. It SHALL
NOT be able to introduce a choice the stored question does not contain, relabel a
stored choice, or cause a value other than the stored one to be submitted.

A position that identifies no stored choice — not an integer, negative, or beyond
the end of the list — SHALL render nothing.

#### Scenario: A program cannot relabel a choice
- **WHEN** a program supplies a label and a value alongside a choice's position
- **THEN** the control SHALL display the stored label
- **AND** activating it SHALL submit the stored value

#### Scenario: A position identifying no stored choice renders nothing
- **WHEN** a program names a choice position that is not an integer, is negative, or
  is beyond the end of the stored choice list
- **THEN** no control SHALL be rendered for it

### Requirement: A program's declared prop types are re-checked when rendering
Every component SHALL re-check its own props against the stored question when it
renders, and SHALL render nothing rather than something ill-defined when a check
fails.

The prop types the component library declares SHALL be treated as a description of
the language for the model, not as a guarantee about what a renderer receives: the
runtime's parser renders permissively and passes malformed props through, so a
declared type alone stops nothing.

#### Scenario: A malformed prop does not reach the rendered output
- **WHEN** a program supplies a choice position of the wrong type
- **THEN** the component SHALL render nothing
- **AND** the surface SHALL NOT display a control derived from that value

### Requirement: A free-text box is offered only when the stored question permits one
Whether a question accepts a free-text answer SHALL be decided by the stored
question, never by the program. A program that asks for a free-text box on a
question whose stored state does not permit free text SHALL render no box, so the
surface never invites an answer the orchestrator would refuse.

#### Scenario: A program cannot add a free-text box
- **WHEN** a program requests a free-text box for a question that does not permit a
  free-text answer
- **THEN** no text field SHALL be rendered

## MODIFIED Requirements

### Requirement: Model-authored question text is rendered as text
The dashboard SHALL render the question text and each choice's label, value, and
description — all of which are authored by the model — as plain text only. It SHALL
NOT render them as markup or markdown, and SHALL NOT interpolate them into an
attribute, a style, or anything else that is executed or resolved as a reference.

This SHALL hold however the surface is produced. Where the surface is rendered from
a program in a UI language, the components resolving that program SHALL pass these
strings as plain text children, and the program itself SHALL NOT contain them.

#### Scenario: Markup in a choice label stays literal
- **WHEN** a choice label contains characters that would form an HTML element
- **THEN** the transcript SHALL display those characters as text
- **AND** no element described by that text SHALL exist in the rendered output

#### Scenario: Markup stays literal through the program renderer
- **WHEN** a question surface rendered from a program displays a question text and a
  choice label that both contain characters forming HTML elements
- **THEN** those characters SHALL appear as text
- **AND** no element described by them SHALL exist in the rendered output
