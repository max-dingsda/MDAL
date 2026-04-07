# Terms and Boundaries

## Purpose of This Chapter

This chapter ensures that central terms in the MDAL documentation are used consistently. Some terms are closely related but deliberately describe different domain or operational facts. Without this distinction, misunderstandings in architecture, implementation, and operational logic arise quickly.

## Fingerprint

The fingerprint is the reference level for expected model behavior in a particular usage context. It is neither merely a prompt, nor simply a set of few-shot examples, nor a policy. Its purpose is the comparative evaluation of responses against a known accepted level.

Rule of thumb:
- Prompt controls generation
- Few-shot demonstrates patterns within the prompt context
- Policy formulates target rules
- Fingerprint provides the operational reference level for evaluation and stabilization

## Transformation

Transformation denotes the targeted reshaping of an already existing model response. The existing result remains the basis, but is adjusted to move closer to the desired reference level or expected form.

Examples:
- linguistic smoothing
- tone adjustment
- formal restructuring of existing content
- correction of individual weaknesses without replacing the response core

Transformation therefore requires a usable initial output.

## Refinement

Refinement denotes the quality-oriented fine-tuning of an already fundamentally usable output. From a domain perspective, refinement is a special case of transformation.

The distinction is most helpful when emphasizing that:
- the response core is already workable
- no coarse reshaping is taking place, but a finer improvement
- the goal is more polish than repair

In short:
- every refinement action is a transformation
- not every transformation is already a refinement

## Retry

Retry denotes a new model run. Unlike transformation and refinement, the existing result is not reworked — instead a new output is requested.

Retry is appropriate when:
- the existing response core is not workable enough
- the deviation from the reference level is too large
- a fresh generation appears more promising than reworking the existing result

## Style Check

Style check means evaluating a response against the known reference level with respect to tonality, response character, external consistency, and proximity to the desired behavior. Style checking is particularly relevant for free-form prose.

Style check is **not** a general domain quality check of content.

## Validation

Validation in MDAL denotes the additional formal or domain-specific check of structured content on the basis of a concrete verification basis, such as:
- schema
- parser
- domain-specific plugin
- rule set

Validation only takes place when such a verification basis is actually present.

## Quality Level vs. Verification Depth

These two terms should not be conflated:

### Quality Level
Describes what result level MDAL aims for in the user experience.

### Verification Depth
Describes how deeply a concrete result can actually be verified in the given context.

A system can therefore have a high target level without being able to examine every response with the same verification depth. This is precisely why the distinction between style checking and plugin-based validation is so important in MDAL.

## Rule of Thumb for the Documentation

When it is unclear which term to use:

- **Fingerprint**, when the operational reference level is meant
- **Transformation**, when an existing output is being reshaped
- **Refinement**, when an already good output is being fine-tuned
- **Retry**, when a new model run takes place
- **Style check**, when free-form prose is evaluated against the reference level
- **Validation**, when structured content is checked using a plugin, schema, or rule set
