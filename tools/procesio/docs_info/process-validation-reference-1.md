# Process Validation — Collected Code Pieces

All the code involved in validating a process in the Process Designer, gathered
into one place for reference. Nothing below is new code — it is copied verbatim
from the source files (paths noted in each section).

> **Reading this file cold?** Start with "Conceptual model" and the "Glossary of
> external helpers" below — they give you the domain model and explain every
> function/type the validation code calls but does not define. Then the call-flow
> diagram and the code sections will make sense on their own.

## What "validating a process" means

A **process** (a.k.a. flow) is a visual graph the user builds on a canvas: **nodes**
(actions) connected by **lines** (transitions). Each node carries **settings** — the
configured inputs for that action (e.g. a URL, a data mapping, a delay value).

Validation answers one question: *"Is this process complete and internally consistent
enough to run?"* It never mutates the process — it only **collects a list of warnings**
(`WarningI[]`). An empty list means valid. The UI later marks the offending nodes with
an error icon and lists the messages. Validation runs over the whole flow (on save /
before run) via `getFlowErrors()`.

There are two independent layers:

1. **Graph-level checks** (structure of the whole flow): is there exactly one Start and
   at least one Stop? Is every node connected? Do subprocess references resolve and map
   their required variables? Are variable names unique?
2. **Field-level checks** (per setting inside each node): required fields filled, values
   match the expected data type, no leftover template placeholders, numeric values in
   range. These are dispatched per setting **type** to a dedicated validator class.

## Conceptual model — the data shapes

The validators walk this structure. Only the fields validation touches are shown.

```ts
// A node = one action box on the canvas
interface Node {
  id: string;              // unique instance id (used as actionId in warnings)
  templateId: string;      // which ACTION this is (Start/Stop/CallApi/Decisional/…) — see §6.1
  name: string;            // user-facing label; "" is invalid
  type: string;            // canvas shape, e.g. "diamond" for decisional
  configuration: SettingTab[]; // tabs, each holding settings[] (the inputs to validate)
  lineArray: Line[];       // transitions attached to this node (connectivity)
  parentId?: string;       // set when the node lives inside a container (e.g. ForEach body)
}

// A transition between two nodes
interface Line {
  nodeStart: Node;
  nodeEnd: Node;
  portData: any;           // portData.isDefault === "error" marks the Error output path
}

// One configured input on a node. `value`'s shape depends on `type`.
interface Setting {
  id: string;              // identifies WHICH setting (see §6.2)
  label: string;           // shown in the warning badge
  type: SettingType;       // selects the validator class (see ControlValidatorFactory)
  value: any;              // string | number | array | object, depending on type
  dataTypeId: string;      // expected data type GUID (see §6.3)
  isList: boolean;         // expects a list vs a scalar
  isRequired?: boolean;
  limits?: { min: number; max: number };
}
```

Key idea for **field validation**: `checkFieldValidation` iterates every
`node.configuration[].settings[]`. For each setting it asks
`ControlValidatorFactory.getValidator(setting.type)` for the right validator, then runs
four independent hooks and concatenates whatever warnings they return:

- `doRequiredCheck`   — is a required value missing/empty?
- `doDataTypeCheck`   — does the value's data type match `setting.dataTypeId`/`isList`?
- `doPlaceholdersCheck` — are there unresolved template placeholders left in the value?
- `doValueCheck`      — is the raw value well-formed for its primitive type (number/int)?

A validator that doesn't care about a given hook returns `[]`. `DefaultControlValidator`
is the fallback for simple settings; the other classes handle complex composite settings
(API payloads, mappings, decisional conditions, delays, …).

## Glossary of external helpers (called but defined elsewhere)

The validation code leans on these. Knowing what they return is enough to follow the logic:

| Symbol | Where | What it does |
|---|---|---|
| `WarningI` | Validation.ts | The warning object every check produces: `{ text, badges, key, actionId? }`. `text` = message, `badges` = breadcrumb chips (action + field), `actionId` = node to highlight. |
| `AbstractControlValidator.getBadges(node, suffix?)` | AbstractControlValidator.ts | Builds the badge array: resolves the action's display name from the store, appends the node's custom name (if different) and an optional ` - <field>` suffix. |
| `createGuid()` | utils/type/guid | Random id; used only as a React-style `key` for each warning. Not domain data. |
| `getValueDataTypes(value)` → `{ scalar: DataModel[], list: DataModel[] }` | Values/ValueDataTypesHelper | Parses a setting's raw string value, finds any **variable references** (GUIDs) inside it, and returns the data types those variables resolve to — split into scalar vs list. Empty arrays = a plain constant with no variables. This is the input to `SettingValidation.validateDataType`. |
| `SettingValidation.validateDataType(types, setting, excluded?)` | SettingValidation.ts (§3) | Returns `true` if the value's actual types (`getValueDataTypes` output) are assignable to what the setting expects (`dataTypeId`, `isList`). Rules: OBJECT accepts anything; STRING accepts any primitive; JSON/OBJECT accept custom models; otherwise ids must match. `excluded` forbids specific type ids (e.g. File). |
| `hasVariable(value)` | Variables/Utils | `true` if the string contains a variable reference (a GUID). Used to **skip** literal-value checks when the value is a variable (its concrete value is unknown at design time). |
| `isPrimitive`, `isCustomTypeAllowed`, `Primitives`, `NonPrimitives` | utils/dataTypeMapper (§6.3) | Data-type GUID helpers/enums. `isCustomTypeAllowed` = the id is JSON or OBJECT. |
| `isValidNumber` / `isValidInteger` | utils/type/* | Primitive value-format checks used by `doValueCheck`. |
| `FormBuilder`, `Validators` | utils/ReactiveForm | A tiny reactive-forms lib. Decisional validators build a throwaway form (one control per condition field with `Validators.required` etc.), call `form.validate()`, and read `form.hasErrors`. It's just a declarative way to check "are all these condition fields filled?". |
| `store.getters.*` | Vuex store | Read-only lookups: `getActionNameById`, `getConditionOperandByName`, `dataTypes` (all `DataModel`s), `processes.variables` (the flow's variables). |
| `OrchestrationService.loadFlow(id)` | services/crud/Orchestration.service | Async: fetches a **subprocess** flow by id, so `checkSubprocess` can confirm it's valid and inspect its input/output variables. |
| template-id / setting-id constants | actionHelper.ts, Utils/Settings.ts (§6.1–6.2) | Opaque GUIDs identifying specific action types and specific settings. Values in §6. |

## Overview / call flow

The entry point is `Designer.component.vue → getFlowErrors()`, which orchestrates
every check via the static `FlowValidation` class. Field-level validation fans out
through `ControlValidatorFactory`, which returns the right `AbstractControlValidator`
subclass per setting type.

```
Designer.getFlowErrors()
 └─ FlowValidation (Validation.ts)
     ├─ noUnconnectedNodes()        graph connectivity
     ├─ checkFieldValidation()      per-setting → ControlValidatorFactory.getValidator()
     │    └─ <Validator>.doRequiredCheck / doDataTypeCheck / doPlaceholdersCheck / doValueCheck
     │         └─ SettingValidation.validateDataType()
     ├─ checkNodeNameValidation()   node names non-empty
     ├─ checkPointsValidation()     exactly 1 start, ≥1 stop
     ├─ checkLimits()               numeric min/max
     ├─ checkSubprocess()           subprocess validity + mappings (async)
     └─ checkVariables()            unique names, primitive-name rules
```

Files consolidated here:

- `src/modules/ProcessDesigner/components/Designer/Designer.component.vue` (invocation)
- `src/modules/ProcessDesigner/Validation/Validation.ts`
- `src/modules/ProcessDesigner/Validation/SettingValidation.ts`
- `src/modules/ProcessDesigner/Validation/ControlValidators/*`
- `src/modules/ProcessDesigner/components/Controls/DecisionalManager/card/DecisionalCard.validation.ts`

---

## 1. Invocation — Designer.component.vue › getFlowErrors()

`src/modules/ProcessDesigner/components/Designer/Designer.component.vue`

```ts
async getFlowErrors() {
  const errors: WarningI[] = [];

  const nodes: Node[] = this.app.getNodes().filter((node: Node) => {
    const actionData = this.actionDataPerId[node.id];
    return !actionData?.isDisabled;
  });

  this.syncDecisionCasesWithLines(nodes);

  // missing transition between 2 actions - an action is not connected to any action
  // no stop node for a branch
  const unconnectedErrors = FlowValidation.noUnconnectedNodes(nodes);

  errors.push(...unconnectedErrors);

  // incomplete actions settings - mandatory input missing for an action
  // invalid input on actions - data mismatch error
  const requiredErrors = FlowValidation.checkFieldValidation(
    nodes,
    this.$store.getters.dataTypes,
    this.$store.state.processes.variables
  );

  errors.push(...requiredErrors);

  const nameErrors = FlowValidation.checkNodeNameValidation(nodes);

  errors.push(...nameErrors);

  const correctPointsErrors = FlowValidation.checkPointsValidation(nodes);

  errors.push(...correctPointsErrors);

  const limitsErrors = FlowValidation.checkLimits(nodes);

  errors.push(...limitsErrors);

  const subprocessErros = await FlowValidation.checkSubprocess(nodes);

  errors.push(
    ...subprocessErros,
    ...FlowValidation.checkVariables(this.variables)
  );

  return errors;
}
```

---

## 2. FlowValidation — Validation.ts

`src/modules/ProcessDesigner/Validation/Validation.ts`

`FlowValidation` is a static class; each method takes the flow's nodes (and sometimes
data types / variables) and returns `WarningI[]`. What each method enforces:

- **`noUnconnectedNodes`** — every node is wired up. Start/Stop need ≥1 line; a normal
  node with only one line that goes to Stop, or none, is incomplete; it must ultimately
  reach a Stop. Error-path lines (`portData.isDefault === "error"`) are excluded so an
  action isn't considered "connected" by its error path alone. Decisional nodes need an
  entry line; ForEach needs its inner Start connected.
- **`checkFieldValidation`** — the field-level layer: dispatches every setting to its
  validator (see §4) and runs the four hooks. Skips array-expansion for decisional/AI
  cases (validated as a whole setting).
- **`checkNodeNameValidation`** — no node may have an empty name.
- **`checkPointsValidation`** — exactly one Start action and at least one Stop action.
- **`checkLimits`** — numeric settings with `limits` must be a number within `[min,max]`.
- **`checkSubprocess`** *(async)* — for Call/Trigger Subprocess nodes: loads the referenced
  flow, requires it to be valid, requires all its **required input variables** to be mapped,
  and checks that mapped variable references actually exist in the subprocess.
- **`checkVariables`** — flow variable names are unique and don't collide with a primitive
  type name unless they are that type.
- `checkDecisional` is a stub (kept for reference; currently a no-op).

```ts
import {
  Line,
  Node,
  ProcessInputOuputSetting,
  Setting,
  SettingType,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import OrchestrationService, {
  VariableType,
  Variable,
} from "@/services/crud/Orchestration.service";
import { ProcessVariable } from "@/services/processvariables/ProcessVariables.model";
import { createGuid } from "@/utils/type/guid";
import mapguid from "@/utils/mapGUIDtoType";
import { typeArray } from "@/utils/mapGUIDtoType";

import { ControlValidatorFactory } from "./ControlValidators/ControlValidatorFactory";
import {
  DECISIONAL_CASE_SETTING,
  SUBPROCESS_SELECT_SETTING,
  SUBPROCESS_SIDE_PANEL_SETTING,
  TRIGGER_SUBPROCESS_SELECT_SETTING,
  TRIGGER_SUBPROCESS_SIDE_PANEL_SETTING,
} from "../components/PropertiesPanel/Utils/Settings";
import {
  FOREACH_TEMPLATE_ID,
  START_ACTION_TEMPLATE_ID,
  CALL_SUBPROCESS_TEMPLATE_ID,
  DECISIONAL_TEMPLATE_ID,
  AI_DECISIONAL_TEMPLATE_ID,
  STOP_ACTION_TEMPLATE_ID,
  TRIGGER_SUBPROCESS_TEMPLATE_ID,
} from "@/utils/actionHelper";
import { DataModel } from "@/services/datamodel/DataModel.model";
import { AbstractControlValidator } from "./ControlValidators/AbstractControlValidator";

export interface WarningI {
  text: string;
  badges: string[];
  key: string;
  actionId?: string;
}
export class FlowValidation {
  static noUnconnectedNodes(actions: Node[]): WarningI[] {
    const unconnectedNodesMessage =
      "Please make sure that all actions are connected.";

    const missingEndNode =
      "Process definition incomplete. Please make sure the action is connected to Stop action.";
    const missingEndNodeExceptErrorPath =
      "Process definition incomplete. Please make sure the action has any connection besides Error path connection.";

    const filterErrorPortLines = (nodeId: string, lines: Line[]) =>
      (Array.isArray(lines) ? lines : []).filter(
        (line) =>
          line.nodeEnd.id === nodeId || line.portData?.isDefault !== "error",
      );

    const errors = actions.reduce((acc: WarningI[], value) => {
      const originalLines = [...value.lineArray];
      const lines = filterErrorPortLines(value.id, originalLines);

      // check start stop
      if (
        value.templateId === START_ACTION_TEMPLATE_ID ||
        value.templateId === STOP_ACTION_TEMPLATE_ID
      ) {
        if (!lines.length) {
          acc.push({
            text: unconnectedNodesMessage,
            badges: AbstractControlValidator.getBadges(value),
            key: createGuid(),
            actionId: value.id,
          });
        }
      } else {
        if (!lines.length) {
          acc.push({
            text: unconnectedNodesMessage,
            badges: AbstractControlValidator.getBadges(value),
            key: createGuid(),
            actionId: value.id,
          });
        } else if (lines.length === 1) {
          if (
            lines[0].nodeStart.templateId === STOP_ACTION_TEMPLATE_ID ||
            lines[0].nodeEnd.templateId === STOP_ACTION_TEMPLATE_ID
          ) {
            acc.push({
              text: unconnectedNodesMessage,
              badges: AbstractControlValidator.getBadges(value),
              key: createGuid(),
              actionId: value.id,
            });
          } else {
            if (!value.parentId) {
              let text = missingEndNode;
              if (lines.length !== originalLines.length) {
                text = missingEndNodeExceptErrorPath;
              }

              acc.push({
                text,
                badges: AbstractControlValidator.getBadges(value),
                key: createGuid(),
                actionId: value.id,
              });
            }
          }
        } else if (
          [DECISIONAL_TEMPLATE_ID, AI_DECISIONAL_TEMPLATE_ID].includes(
            value.templateId,
          ) &&
          lines.length >= 2
        ) {
          // check if conditional has entry node
          let isValid = false;

          lines.forEach((line) => {
            if (line.nodeEnd.id === value.id) {
              isValid = true;
            }
          });

          if (!isValid) {
            acc.push({
              text: unconnectedNodesMessage,
              badges: AbstractControlValidator.getBadges(value),
              key: createGuid(),
              actionId: value.id,
            });
          }
        } else if (value.templateId === FOREACH_TEMPLATE_ID) {
          const foreachStart = (value as any).children.find(
            (c: Node) => c?.templateId === START_ACTION_TEMPLATE_ID,
          );
          if (foreachStart && !foreachStart.lineArray.length) {
            acc.push({
              text: unconnectedNodesMessage,
              badges: AbstractControlValidator.getBadges(value),
              key: createGuid(),
              actionId: value.id,
            });
          }
        }
      }

      return acc;
    }, []);

    return errors;
  }

  static checkFieldValidation(
    actions: Node[],
    dataType: DataModel[],
    processVariables: ProcessVariable[],
  ): WarningI[] {
    const errors: WarningI[] = [];

    actions.forEach((node) => {
      node.configuration.forEach((config) => {
        config.settings.forEach((setting) => {
          const settingValues =
            Array.isArray(setting.value) &&
            setting.id !== DECISIONAL_CASE_SETTING && // this is an exception for the decision case validation
            setting.type !== SettingType.AI_DECISIONAL_CASE // AI Decisional cases are validated as a whole setting
              ? setting.value
              : [setting];

          settingValues.forEach((val) => {
            const validator = ControlValidatorFactory.getValidator(val.type);
            errors.push(
              ...[
                ...validator.doRequiredCheck(node, val),
                ...validator.doDataTypeCheck(
                  node,
                  val,
                  dataType,
                  processVariables,
                ),
                ...validator.doPlaceholdersCheck(node, val),
                ...validator.doValueCheck(node, val),
              ],
            );
          });
        });
      });
    });

    return errors;
  }

  static checkNodeNameValidation(actions: Node[]): WarningI[] {
    const errors: WarningI[] = [];

    actions.forEach((node) => {
      if (node.name == "") {
        errors.push({
          text: "Please make sure that all actions have a name.",
          badges: AbstractControlValidator.getBadges(node, " - node name"),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  static checkDecisional(actions: Node[]): WarningI[] {
    const errors: WarningI[] = [];

    actions.forEach((node) => {
      if (node.type === "diamond") {
        node.configuration.forEach((config) => {
          config.settings.forEach((setting) => {
            if (setting.value) {
              //TODO: call new validation error
            }
          });
        });
      }
    });

    return errors;
  }

  static checkLimits(actions: Node[]): WarningI[] {
    const errors: WarningI[] = [];
    actions.forEach((node) => {
      node.configuration.forEach((config) => {
        config.settings.forEach((setting) => {
          const settings = Array.isArray(setting.value)
            ? setting.value
            : [setting];

          settings.forEach((setting) => {
            if (
              setting.limits &&
              (setting.value < setting.limits.min ||
                setting.value > setting.limits.max)
            ) {
              if (isNaN(setting.value)) {
                errors.push({
                  text: `Please make sure that the value is a number.`,
                  badges: AbstractControlValidator.getBadges(
                    node,
                    ` - ${setting.label}`,
                  ),
                  key: createGuid(),
                  actionId: node.id,
                });
              }
              errors.push({
                text: `Please make sure that the value is between ${setting.limits.min} and ${setting.limits.max}.`,
                badges: AbstractControlValidator.getBadges(
                  node,
                  ` - ${setting.label}`,
                ),
                key: createGuid(),
                actionId: node.id,
              });
            }
          });
        });
      });
    });

    return errors;
  }

  static checkPointsValidation(actions: Node[]): WarningI[] {
    const missingStartError =
      "Please make sure that the process have 1 start action";

    const missingStopError =
      "Please make sure that the process have at least 1 stop action";
    const errors: WarningI[] = [];

    const startNode = actions.filter(
      (node) => node.templateId === "c0e32108-6e3e-4ab8-96bd-cd61be6edb33",
    );

    const endNodes = actions.filter(
      (node) => node.templateId === "c0e32108-6e3e-4ab8-96bd-cd61be6edb34",
    );

    if (startNode.length !== 1) {
      errors.push({
        text: missingStartError,
        badges: ["Start"],
        key: createGuid(),
      });
    }

    if (endNodes.length < 1) {
      errors.push({
        text: missingStopError,
        badges: ["Stop"],
        key: createGuid(),
      });
    }

    return errors;
  }

  static async checkSubprocess(actions: Node[]): Promise<WarningI[]> {
    const errors: WarningI[] = [];

    for (let index = 0; index < actions.length; index++) {
      const action = actions[index];

      if (
        ![CALL_SUBPROCESS_TEMPLATE_ID, TRIGGER_SUBPROCESS_TEMPLATE_ID].includes(
          action.templateId,
        )
      ) {
        continue;
      }

      const subprocessNode: Node | undefined = action;

      /** id of select component */
      const selectSubprocess: Setting | undefined =
        action.configuration[0].settings.find((setting) =>
          [
            SUBPROCESS_SELECT_SETTING,
            TRIGGER_SUBPROCESS_SELECT_SETTING,
          ].includes(setting.id),
        );

      const subprocessValue = action.configuration[0].settings.find((setting) =>
        [
          SUBPROCESS_SIDE_PANEL_SETTING,
          TRIGGER_SUBPROCESS_SIDE_PANEL_SETTING,
        ].includes(setting.id),
      )?.value;

      /** id of the sidepanel holding the input and output variables */
      const subprocessInput: ProcessInputOuputSetting | undefined =
        subprocessValue?.length && subprocessValue[0];
      const subprocessOutput: ProcessInputOuputSetting | undefined =
        subprocessValue?.length && subprocessValue[1];

      if (selectSubprocess?.value) {
        const response = await OrchestrationService.loadFlow(
          selectSubprocess.value,
        );

        if (response.content) {
          const inputVariables: Variable[] = [];
          const outputVariables: Variable[] = [];

          const process = response.content.flow;

          if (process && !process.isValid) {
            errors.push({
              text: "Subprocess should be valid.",
              badges: subprocessNode
                ? AbstractControlValidator.getBadges(subprocessNode)
                : [],
              key: createGuid(),
              actionId: subprocessNode?.id,
            });
          }

          process?.variables?.forEach((variable) => {
            if (variable.type === VariableType.INPUT) {
              inputVariables.push(variable);
            }

            if (variable.type === VariableType.OUTPUT) {
              outputVariables.push(variable);
            }
          });

          inputVariables
            .filter((variable) => variable.isRequired)
            .forEach((requiredInputVariable) => {
              const inputs = subprocessInput?.value || [];
              const mapIndex = inputs.findIndex(
                (input) =>
                  input.subprocess === requiredInputVariable.id &&
                  !!input.process,
              );

              if (mapIndex === -1) {
                errors.push({
                  text: `Mapping of required subprocess variable (<b>${requiredInputVariable.name}</b>) is missing.`,
                  badges: subprocessNode
                    ? AbstractControlValidator.getBadges(subprocessNode)
                    : [],
                  key: createGuid(),
                  actionId: subprocessNode?.id,
                });
              }
            });

          const variableRegex =
            /([0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}(\.[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12})*)\b(?!\.)/g;

          (subprocessInput?.value || [])?.forEach((input) => {
            const variables = input.subprocess.match(new RegExp(variableRegex));

            if (variables) {
              variables.forEach((matchedVariable) => {
                const guidArray = matchedVariable.split(".");

                const isValid =
                  inputVariables
                    .map((variable) => variable.id)
                    .indexOf(guidArray[0]) >= 0;

                if (!isValid) {
                  errors.push({
                    text: `Check data mapping.`,
                    badges: subprocessNode
                      ? AbstractControlValidator.getBadges(subprocessNode)
                      : [],
                    key: createGuid(),
                    actionId: subprocessNode?.id,
                  });
                }
              });
            }
          });

          if (Array.isArray(subprocessOutput?.value)) {
            (subprocessOutput?.value || []).forEach((input) => {
              const variables = input.subprocess.match(
                new RegExp(variableRegex),
              );

              if (variables) {
                variables.forEach((matchedVariable) => {
                  const guidArray = matchedVariable.split(".");

                  const isValid =
                    outputVariables
                      .map((variable) => variable.id)
                      .indexOf(guidArray[0]) >= 0;

                  if (!isValid) {
                    errors.push({
                      text: `Check data mapping.`,
                      badges: subprocessNode
                        ? AbstractControlValidator.getBadges(subprocessNode)
                        : [],
                      key: createGuid(),
                      actionId: subprocessNode?.id,
                    });
                  }
                });
              }
            });
          }
        }
      }
    }

    return errors;
  }

  static checkVariables(variables: Variable[]): WarningI[] {
    const errors: WarningI[] = [];

    // store already found duplicates to do not show same message few times
    const duplicates: string[] = [];

    variables.forEach((variable: Variable) => {
      const sameNameVariableIndex = variables.findIndex(
        (v) => v.name === variable.name && v.id !== variable.id,
      );
      if (
        sameNameVariableIndex !== -1 &&
        duplicates.indexOf(variable.name) === -1
      ) {
        errors.push({
          text: "Variable name should be unique.",
          badges: [`Variable: ${variable.name}`],
          key: createGuid(),
        });
        duplicates.push(variable.name);
      }

      const typeName = mapguid(variable);

      typeArray.forEach((option: string) => {
        if (variable.name.toLowerCase() == option) {
          if (typeName != "custom") {
            if (typeName != variable.name.toLowerCase()) {
              errors.push({
                text: `Cannot name variables as Primitives with a different type.`,
                badges: [`Variable: ${variable.name}`],
                key: createGuid(),
              });
            }
          }
        }
      });
    });

    return errors;
  }
}
```

---

## 3. SettingValidation — data-type matching

`src/modules/ProcessDesigner/Validation/SettingValidation.ts`

```ts
import { ValueDataTypes } from "@/modules/ProcessDesigner/Values/ValueDataTypesHelper";
import {
  isCustomTypeAllowed,
  isPrimitive,
  NonPrimitives,
  Primitives,
} from "@/utils/dataTypeMapper";
import { Setting } from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { DataModel } from "@/services/datamodel/DataModel.model";

export class SettingValidation {
  static validateDataType(
    { scalar: scalarDataTypes, list: listDataTypes }: ValueDataTypes,
    setting: Setting,
    excludedDataTypesId: string[] = []
  ): boolean {
    if (scalarDataTypes.length === 0 && listDataTypes.length === 0) {
      return true;
    }

    // check for list type
    if (
      (setting.isList &&
        (scalarDataTypes.length !== 0 || listDataTypes.length !== 1)) ||
      (!setting.isList &&
        (scalarDataTypes.length === 0 || listDataTypes.length !== 0))
    ) {
      return false;
    }

    const settingDataTypeId = setting.dataTypeId;

    const validTypeFlags = [...scalarDataTypes, ...listDataTypes]
      .filter((dataType) => !!dataType)
      .reduce((flags: boolean[], dataType: DataModel) => {
        let flag = false;

        if (excludedDataTypesId.includes(dataType.id)) {
          flag = false;
        }
        // Object data type means any type is allowed
        else if (settingDataTypeId === NonPrimitives.OBJECT) {
          flag = true;
        } else if (isPrimitive(dataType.id)) {
          flag =
            settingDataTypeId === Primitives.STRING
              ? true
              : dataType.id === settingDataTypeId;
        } else {
          flag =
            isCustomTypeAllowed(settingDataTypeId) ||
            dataType.id === settingDataTypeId;
        }

        flags.push(flag);
        return flags;
      }, []);

    return validTypeFlags.every((flag: boolean) => flag);
  }
}
```

---

## 4. ControlValidators

Each setting **type** maps to one validator class (via `ControlValidatorFactory`, §4.2).
The class implements the four hooks; anything it doesn't check returns `[]`. What each
one guards:

| Setting type (§6.4) | Validator (§) | Guards against |
|---|---|---|
| *(fallback / simple inputs)* | DefaultControlValidator (4.3) | required-but-empty; value's variable types not assignable to the field; malformed number/integer/object literals |
| `AI_DECISIONAL_CASE` | AiDecisionalCaseValidator (4.4) | any AI case missing name, condition, or target |
| `TABS_PAYLOAD` (Call API v2) | TabsPayloadControlValidator (4.5) | body/query/header row has a value but no key; body item type mismatch (form-data/urlencoded/binary) |
| `TABS_PAYLOAD_OLD` (Call API legacy) | TabsPayloadOldControlValidator (4.6) | query/header row has a value but no key |
| `PROCESS_INPUT` / `PROCESS_OUTPUT` | ProcessInputOutputValidator (4.7) | subprocess mapping row missing its subprocess side (type-check currently disabled) |
| `DECISIONAL_CASE` | ConditionalValidator (4.8) | case missing name/target/≥1 condition; left/right operand type mismatch; missing operator |
| `DATA_STORE_DECISIONAL` | DataStoreDecisionalValidator (4.9) | "Where" conditions not fully configured (extends ConditionalValidator) |
| `DELAY_DEFINITION` | DelayDefinitionValidator (4.10) | delay value missing; negative wait-for; wait-until date in the past |
| `DOCUMENT_MAPPER_BUILDER` / `DATA_STORE_MAPPER` | DocumentMapperValidator (4.11) | mapper row missing its document target (type-check currently disabled) |
| `COLUMN_DEFINITION` (Get File Data) | ColumnDefinitionControlValidator (4.12) | no rows, or a row missing column name / attribute; attribute type mismatch |
| `MAP_PARAMETERS` | MapParametersValidator (4.13) | mapping row missing destination/source |
| `MAP_PROCESS_DATA` | MapProcessDataValidator (4.14) | mapping row missing destination/source; source→destination type mismatch (File→File allowed) |

Note: several `doDataTypeCheck` bodies are intentionally disabled (return `[]` with the
old implementation left commented out) — flagged inline where that's the case.

### 4.1 AbstractControlValidator (base class)

`src/modules/ProcessDesigner/Validation/ControlValidators/AbstractControlValidator.ts`

```ts
import {
  Node,
  Setting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { WarningI } from "../Validation";

import { DataModel } from "@/services/datamodel/DataModel.model";
import { ProcessVariable } from "@/services/processvariables/ProcessVariables.model";
import { createGuid } from "@/utils/type/guid";
import { store } from "@/store";
export abstract class AbstractControlValidator {
  // messages are customizable with the methods below
  requiredCheckErrorMessage =
    "Please make sure that the action is defined/configured properly.";

  typeCheckErrorMessage = "Error: data type mismatch.";

  placeholdersCheckErrorMessage =
    "Please replace all placeholders in the template.";

  setRequiredCheckErrorMessage(message: string) {
    this.requiredCheckErrorMessage = message;
  }

  setTypeCheckErrorMessage(message: string) {
    this.typeCheckErrorMessage = message;
  }

  // if a control should not be checked for requiring - implement the method and return an empty array
  abstract doRequiredCheck(node: Node, setting: Setting): WarningI[];

  // if a control should not be checked for types - implement the method and return an empty array
  abstract doDataTypeCheck(
    node: Node,
    setting: Setting,
    dataType?: DataModel[],
    processVariables?: ProcessVariable[]
  ): WarningI[];

  doPlaceholdersCheck(node: Node, setting: Setting): WarningI[] {
    const errors: WarningI[] = [];

    if (setting.value) {
      let value = setting.value;
      if (typeof value === "object") {
        value = JSON.stringify(value);
      }

      if (
        typeof value === "string" &&
        (this.hasPlaceholder(value) || value.includes("<%%>"))
      )
        errors.push({
          text: this.placeholdersCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label}`
          ),
          key: createGuid(),
          actionId: node.id,
        });
    }

    return errors;
  }

  getAllSettings(node: Node) {
    const settings: Setting[] = [];

    const getSettings = (setting: Setting) => {
      if (typeof setting.id !== "undefined") {
        settings.push(setting);
        if (Array.isArray(setting.value)) {
          setting.value.forEach((setting: Setting) => {
            getSettings(setting);
          });
        }
      }
    };

    // get settings recursively
    node.configuration.forEach((config) => {
      config.settings.forEach((setting: Setting) => {
        getSettings(setting);
      });
    });

    return settings;
  }

  hasPlaceholder(value: string) {
    return new RegExp(
      /([x]{8}\-[x]{4}\-[x]{4}\-[x]{4}\-[a-zA-Z]{11}(\.[x]{8}\-[x]{4}\-[x]{4}\-[x]{4}\-[a-zA-Z]{11})*)\b(?!\.)/g
    ).test(value);
  }

  abstract doValueCheck(node: Node, setting: Setting): WarningI[];

  // badge should have action type with messsage and actual node name (if it differs from action type)
  // check PRC-3091 for reference
  static getBadges(node: Node, additionalMesage = "") {
    const actionName = store.getters.getActionNameById(node.templateId);

    if (!actionName) {
      return [node.name + additionalMesage];
    }

    const badges = [];

    if (node.name && actionName.trim() !== node.name.trim()) {
      badges.push(node.name);
    }

    badges.push(actionName + additionalMesage);

    return badges;
  }
}
```

### 4.2 ControlValidatorFactory

`src/modules/ProcessDesigner/Validation/ControlValidators/ControlValidatorFactory.ts`

```ts
import { SettingType } from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { AbstractControlValidator } from "./AbstractControlValidator";
import { TabsPayloadControlValidator } from "./CallApiAction/TabsPayloadControlValidator";
import { TabsPayloadOldControlValidator } from "./CallApiAction/TabsPayloadOldControlValidator";
import { ProcessInputOutputValidator } from "./CallSubprocess/ProcessInputOutputValidator";
import { ConditionalValidator } from "./DecisionalAction/ConditionsValidator";
import { DefaultControlValidator } from "./DefaultControlValidator";
import { DelayDefinitionValidator } from "./DelayAction/DelayDefinitionValidator";
import { DocumentMapperValidator } from "./DocumentMapper/DocumentMapperValidator";
import { ColumnDefinitionControlValidator } from "./GetFileData/ColumnDefinitionControlValidator";
import { MapParametersValidator } from "./MapParameters/MapParametersValidator";
import { AiDecisionalCaseValidator } from "./AiDecisionalAction/AiDecisionalCaseValidator";
import { MapProcessDataValidator } from "./MapProcessData/MapProcessDataValidator";
import { DataStoreDecisionalValidator } from "./DataStoreDecisional/DataStoreDecisionalValidator";

export class ControlValidatorFactory {
  static getValidator(settingType: SettingType): AbstractControlValidator {
    switch (settingType) {
      case SettingType.TABS_PAYLOAD_OLD:
        return new TabsPayloadOldControlValidator();
      case SettingType.TABS_PAYLOAD:
        return new TabsPayloadControlValidator();
      case SettingType.COLUMN_DEFINITION:
        return new ColumnDefinitionControlValidator();
      case SettingType.DELAY_DEFINITION:
        return new DelayDefinitionValidator();
      case SettingType.PROCESS_INPUT:
      case SettingType.PROCESS_OUTPUT:
        return new ProcessInputOutputValidator();
      case SettingType.MAP_PROCESS_DATA:
        return new MapProcessDataValidator();
      case SettingType.MAP_PARAMETERS:
        return new MapParametersValidator();
      case SettingType.DECISIONAL_CASE:
        return new ConditionalValidator();
      case SettingType.DATA_STORE_DECISIONAL:
        return new DataStoreDecisionalValidator();
      case SettingType.AI_DECISIONAL_CASE:
        return new AiDecisionalCaseValidator();
      case SettingType.DOCUMENT_MAPPER_BUILDER:
      case SettingType.DATA_STORE_MAPPER:
        return new DocumentMapperValidator();
      default:
        return new DefaultControlValidator();
    }
  }
}
```

### 4.3 DefaultControlValidator

`src/modules/ProcessDesigner/Validation/ControlValidators/DefaultControlValidator.ts`

```ts
import {
  Node,
  Setting,
  SettingType,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { NonPrimitives, Primitives } from "@/utils/dataTypeMapper";
import { createGuid } from "@/utils/type/guid";
import { isValidInteger } from "@/utils/type/integer";
import { parseJSON } from "@/utils/type/json";
import { isValidNumber } from "@/utils/type/number";
import { getValueDataTypes } from "../../Values/ValueDataTypesHelper";
import { hasVariable } from "../../Variables/Utils";
import { SettingValidation } from "../SettingValidation";
import { WarningI } from "../Validation";
import { AbstractControlValidator } from "./AbstractControlValidator";

export class DefaultControlValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: Setting): WarningI[] {
    const errors = [];
    const value = setting.value;
    const isEmpty =
      value === null ||
      typeof value === "undefined" ||
      value === "" ||
      (Array.isArray(value) && value.length === 0);

    if (setting.isRequired && isEmpty) {
      errors.push({
        text: this.requiredCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    return errors;
  }

  doDataTypeCheck(node: Node, setting: Setting): WarningI[] {
    const value = setting.value || "";

    if (typeof value !== "string") {
      return [];
    }

    const errors = [];
    if (
      !SettingValidation.validateDataType(getValueDataTypes(value), setting)
    ) {
      errors.push({
        text: this.typeCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    return errors;
  }

  doValueCheck(node: Node, setting: Setting): WarningI[] {
    const errors: WarningI[] = [];

    if (
      setting.value === null ||
      typeof setting.value === "undefined" ||
      hasVariable(setting.value)
    ) {
      return [];
    }

    let valuesList: any[] | string = setting.isList
      ? setting.value
      : [setting.value];

    if (!Array.isArray(valuesList)) {
      const parsedValuesList = parseJSON(
        typeof valuesList === "string"
          ? valuesList.replace(/'/g, '"')
          : valuesList
      );

      if (Array.isArray(parsedValuesList)) {
        valuesList = parsedValuesList;
      }
    }

    switch (setting.dataTypeId) {
      case Primitives.FLOAT:
      case Primitives.DOUBLE:
      case Primitives.NUMBER: {
        if (
          !Array.isArray(valuesList) ||
          !valuesList.every((item) => isValidNumber(item))
        ) {
          errors.push({
            text: `Please make sure that the value is a number.`,
            badges: AbstractControlValidator.getBadges(
              node,
              ` - ${setting.label}`
            ),
            key: createGuid(),
            actionId: node.id,
          });
        }
        break;
      }

      case Primitives.INTEGER:
        if (
          !Array.isArray(valuesList) ||
          !valuesList.every((item) => isValidInteger(item))
        ) {
          errors.push({
            text: `Please make sure that the value is an integer.`,
            badges: AbstractControlValidator.getBadges(
              node,
              ` - ${setting.label}`
            ),
            key: createGuid(),
            actionId: node.id,
          });
        }
        break;

      case NonPrimitives.OBJECT:
        if (
          (!Array.isArray(valuesList) ||
            !valuesList.every((item) => isValidNumber(item))) &&
          setting.type == SettingType.NUMBER
        ) {
          errors.push({
            text: `Please make sure that the value is a number.`,
            badges: AbstractControlValidator.getBadges(
              node,
              ` - ${setting.label}`
            ),
            key: createGuid(),
            actionId: node.id,
          });
        }
        break;
    }

    return errors;
  }
}
```

### 4.4 AiDecisionalCaseValidator

`src/modules/ProcessDesigner/Validation/ControlValidators/AiDecisionalAction/AiDecisionalCaseValidator.ts`

```ts
import {
  Node,
  Setting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";
import { AiDecisionalCardValue } from "@/modules/ProcessDesigner/components/Controls/AiDecisionalManager/AiDecisional.model";
import { createGuid } from "@/utils/type/guid";
import { DataModel } from "@/services/datamodel/DataModel.model";
import { ProcessVariable } from "@/services/processvariables/ProcessVariables.model";

const message =
  "Action definition incomplete. Please make sure all AI cases have a name, condition, and target configured.";

export class AiDecisionalCaseValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: Setting): WarningI[] {
    const errors: WarningI[] = [];
    const value = setting.value as AiDecisionalCardValue[];

    if (!value || !Array.isArray(value) || value.length === 0) {
      return [];
    }

    const hasIncomplete = value.some(
      (caseItem) =>
        !caseItem.name?.trim() ||
        !caseItem.condition?.trim() ||
        !caseItem.target
    );

    if (hasIncomplete) {
      errors.push({
        text: message,
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    return errors;
  }

  doDataTypeCheck(
    _node: Node,
    _setting: Setting,
    _dataType?: DataModel[],
    _processVariables?: ProcessVariable[]
  ): WarningI[] {
    return [];
  }

  doValueCheck(_node: Node, _setting: Setting): WarningI[] {
    return [];
  }
}
```

### 4.5 TabsPayloadControlValidator (Call API)

`src/modules/ProcessDesigner/Validation/ControlValidators/CallApiAction/TabsPayloadControlValidator.ts`

```ts
import {
  Node,
  RequestPayloadSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { getValueDataTypes } from "@/modules/ProcessDesigner/Values/ValueDataTypesHelper";
import {
  PayloadBodyTypeLabels,
  PayloadBodyTypes,
  TabsPayloadItem,
  TabsPayloadItemType,
} from "@/services/apiCall/tabsPayload/TabsPayload.model";
import { NonPrimitives } from "@/utils/dataTypeMapper";
import { createGuid } from "@/utils/type/guid";
import cloneDeep from "lodash/cloneDeep";
import { SettingValidation } from "../../SettingValidation";
import { WarningI } from "../../Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

export class TabsPayloadControlValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: RequestPayloadSetting): WarningI[] {
    const value = setting.value;
    const activeBodyValue = value?.body.value[value?.body.type];
    const queryParams = value?.queryParams || [];
    const headers = value?.headers || [];
    const errors: WarningI[] = [];

    if (Array.isArray(activeBodyValue)) {
      activeBodyValue.forEach((item: TabsPayloadItem, rowIndex) => {
        if (
          item.value && item.value.length > 0 &&
          (!item.key || item.key.trim().length === 0)
        ) {
          errors.push({
            text: this.requiredCheckErrorMessage,
            badges: AbstractControlValidator.getBadges(
              node,
              ` - ${setting.label} (Body: ${
                PayloadBodyTypeLabels[value.body.type]
              }, row ${rowIndex + 1})`
            ),
            key: createGuid(),
            actionId: node.id,
          });
        }
      });
    }

    queryParams.forEach((param, rowIndex) => {
      if (
        param.value && param.value.length > 0 &&
        (!param.key || param.key.trim().length === 0)
      ) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (Query Params, row ${rowIndex + 1})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    headers.forEach((header, rowIndex) => {
      if (
        header.value &&
        header.value.length > 0 &&
        (!header.key || header.key.trim().length === 0)
      ) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (Headers, row ${rowIndex + 1})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doDataTypeCheck(node: Node, setting: RequestPayloadSetting): WarningI[] {
    setting = cloneDeep(setting);

    const value = setting.value;
    const activeBodyValue = value?.body.value[value?.body.type];

    const errors: WarningI[] = [];

    if (Array.isArray(activeBodyValue)) {
      activeBodyValue.forEach((item: TabsPayloadItem, rowIndex) => {
        const originalSettingListState = setting.isList;
        const originalSettingDataTypeId = setting.dataTypeId;

        const inputTypes = getValueDataTypes(item.value);

        if (value.body.type === PayloadBodyTypes.FORM_DATA) {
          if (item.type === TabsPayloadItemType.FILE) {
            setting.isList = inputTypes.list.length > 0;
            setting.dataTypeId = NonPrimitives.FILE;
          } else {
            setting.isList = inputTypes.list.length > 0;
            setting.dataTypeId = NonPrimitives.OBJECT;
          }

          if (
            !SettingValidation.validateDataType(
              inputTypes,
              setting,
              item.type === TabsPayloadItemType.FILE ? [] : [NonPrimitives.FILE]
            )
          ) {
            errors.push({
              text: this.typeCheckErrorMessage,
              badges: AbstractControlValidator.getBadges(
                node,
                ` - ${setting.label} (Body: ${
                  PayloadBodyTypeLabels[value.body.type]
                }, row ${rowIndex + 1})`
              ),
              key: createGuid(),
              actionId: node.id,
            });
          }
        } else if (value.body.type === PayloadBodyTypes.X_WWW_FORM_URLENCODED) {
          setting.isList = inputTypes.list.length > 0;
          setting.dataTypeId = NonPrimitives.OBJECT;

          if (
            !SettingValidation.validateDataType(
              inputTypes,
              setting,
              [NonPrimitives.FILE] // file is not allowed
            )
          ) {
            errors.push({
              text: this.typeCheckErrorMessage,
              badges: AbstractControlValidator.getBadges(
                node,
                ` - ${setting.label} (Body: ${
                  PayloadBodyTypeLabels[value.body.type]
                }, row ${rowIndex + 1})`
              ),
              key: createGuid(),
              actionId: node.id,
            });
          }
        }

        // reset setting props to original state
        setting.isList = originalSettingListState;
        setting.dataTypeId = originalSettingDataTypeId;
      });
    } else if (
      typeof activeBodyValue === "string" &&
      value.body.type === PayloadBodyTypes.BINARY
    ) {
      const inputTypes = getValueDataTypes(activeBodyValue);
      if (!SettingValidation.validateDataType(inputTypes, setting)) {
        errors.push({
          text: this.typeCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (Body: ${
              PayloadBodyTypeLabels[value.body.type]
            })`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    }

    return errors;
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.6 TabsPayloadOldControlValidator (Call API, legacy)

`src/modules/ProcessDesigner/Validation/ControlValidators/CallApiAction/TabsPayloadOldControlValidator.ts`

```ts
import {
  Node,
  RequestPayloadOldSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "../../Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

export class TabsPayloadOldControlValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: RequestPayloadOldSetting): WarningI[] {
    const value = setting.value;
    const queryParams = value.queryParams;
    const headers = value.headers;
    const errors: WarningI[] = [];

    queryParams.forEach((param) => {
      if (
        param.value && param.value.length > 0 &&
        (!param.key || param.key.trim().length === 0)
      ) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (Query Params)`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    headers.forEach((header) => {
      if (
        header.value && header.value.length > 0 &&
        (!header.key || header.key.trim().length === 0)
      ) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (Headers)`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doDataTypeCheck(): WarningI[] {
    return [];
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.7 ProcessInputOutputValidator (Call Subprocess)

`src/modules/ProcessDesigner/Validation/ControlValidators/CallSubprocess/ProcessInputOutputValidator.ts`
(`doDataTypeCheck` body is a large commented-out block, omitted here — currently returns `[]`.)

```ts
import {
  Node,
  ProcessInputOuputSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

export class ProcessInputOutputValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: ProcessInputOuputSetting): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value;

    if (!value) {
      errors.push({
        text: this.requiredCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        return [];
      }

      value.forEach((row, rowIndex) => {
        if (!row.subprocess || row.subprocess.trim().length === 0) {
          errors.push({
            text: this.requiredCheckErrorMessage,
            badges: AbstractControlValidator.getBadges(
              node,
              ` - ${setting.label} (row ${rowIndex + 1})`
            ),
            key: createGuid(),
            actionId: node.id,
          });
        }
      });
    }

    return errors;
  }

  doDataTypeCheck(): WarningI[] {
    return [];
    // ... (data-type check currently commented out)
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.8 ConditionalValidator (Decisional cases)

`src/modules/ProcessDesigner/Validation/ControlValidators/DecisionalAction/ConditionsValidator.ts`

```ts
import {
  Node,
  ProcessInputOuputSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

import DecisionalCardValidation from "@/modules/ProcessDesigner/components/Controls/DecisionalManager/card/DecisionalCard.validation";

import { ProcessVariable } from "@/services/processvariables/ProcessVariables.model";
import { Primitives } from "@/utils/dataTypeMapper";
import { Condition } from "@/modules/ProcessDesigner/components/Controls/DecisionalManager/Decisional.model";
import { isBoolean } from "@/utils/type/boolean";
import { isNullOrUndefined } from "@/utils/type/nullUndefined";
import { DataModel } from "@/services/datamodel/DataModel.model";
import { OperatorName } from "@/services/actionlist/ActionList.service";

const message =
  "Action definition incomplete. Please make sure all cases are configured.";

export class ConditionalValidator extends AbstractControlValidator {
  typeCheckErrorMessage = "Please make sure condition's types match.";

  doRequiredCheck(node: Node, setting: ProcessInputOuputSetting): WarningI[] {
    const errors: WarningI[] = [];

    let hasErrors = false;

    const value = setting.value;

    if (!value || value.length === 0) {
      return [];
    }

    Array.isArray(value) &&
      value.forEach((_setting: any) => {
        hasErrors = DecisionalCardValidation(_setting);
      });

    if (hasErrors) {
      errors.push({
        text: message,
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    return errors;
  }

  doDataTypeCheck(
    node: Node,
    setting: ProcessInputOuputSetting,
    dataType: DataModel[],
    processVariables: ProcessVariable[]
  ): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value;

    if (!value || value.length === 0) {
      return [];
    }

    const hasErrors = this.checkConditionsType(
      value[0].condition,
      dataType,
      processVariables
    );

    if (hasErrors.hasConditionErrors) {
      errors.push({
        text: this.typeCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    if (hasErrors.hasOperatorErrors) {
      errors.push({
        text: "Please make sure condition's operators are set.",
        badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
        key: createGuid(),
        actionId: node.id,
      });
    }

    return errors;
  }

  getCurrentType(
    dataTypes: DataModel[],
    conditionId: string,
    pV: ProcessVariable[]
  ) {
    const attribute = (conditionId || "").split(".");

    const firstId = attribute[0];

    const f = pV.find((p) => {
      return firstId.includes(p.id);
    });

    const dataType = f?.dataType;

    const dataTypeOperator = this.findDataType(
      dataType as string,
      dataTypes,
      conditionId
    );

    return dataTypeOperator ? dataTypeOperator : f ? f.dataType : null;
  }

  isVariableList(varTree: string, pV: any, dataTypes: DataModel[]) {
    const varTreeAsArray = varTree.split(".");

    const variableId = varTreeAsArray[0];

    const variable = pV.find((val: any) => val.id === variableId);

    if (variable) {
      if (varTreeAsArray.length === 1) {
        return variable.isList;
      }

      let variableDataType: DataModel | undefined = dataTypes.find(
        (type: DataModel) => type.id === variable.dataType
      );

      let attribute: any;

      varTreeAsArray.slice(1).forEach((attrId) => {
        attribute = (variableDataType?.attributes || []).find(
          (attr) => attr.id === attrId
        );

        variableDataType = dataTypes.find(
          (type: DataModel) => type.id === attribute?.dataTypeId
        );
      });

      if (attribute) {
        return attribute.isList;
      }

      return false;
    }

    return false;
  }

  findDataType(
    dataType: string,
    dataTypes: DataModel[],
    conditionId: string
  ): null | string {
    const attribute = (conditionId || "").split(".");
    const lastId = attribute[attribute.length - 1];
    for (let j = 0; j < dataTypes.length; j++) {
      const dt = dataTypes[j];
      if (dt.id === dataType) {
        for (let i = 0; i < (dt.attributes || []).length; i++) {
          const propList = dt.attributes[i];

          if (lastId.includes(propList.id)) {
            return propList.dataTypeId;
          } else {
            const findDataType = this.findDataType(
              propList.dataTypeId,
              dataTypes,
              conditionId
            );

            if (findDataType) {
              return findDataType;
            }
          }
        }
      }
    }

    return null;
  }

  checkConditionsType(
    conditions: Condition[],
    dataType: DataModel[],
    processVariables: ProcessVariable[]
  ): {
    hasConditionErrors: boolean;
    hasOperatorErrors: boolean;
  } {
    let hasConditionErrors = false;
    let hasOperatorErrors = false;

    conditions.forEach((_condition: any) => {
      let leftType, rightType;

      if (_condition.leftOperator || _condition.rightOperator) {
        if (!_condition.operator) {
          hasOperatorErrors = true;
        }
        //attribute vs atribute check
        const leftAttributeType = this.getCurrentType(
          dataType,
          _condition.leftOperator.value,
          processVariables
        );

        const rightAttributeType = this.getCurrentType(
          dataType,
          _condition.rightOperator.value,
          processVariables
        );

        if (leftAttributeType !== null && rightAttributeType !== null) {
          if (leftAttributeType !== rightAttributeType) {
            hasConditionErrors = true;
          }
        }

        if (_condition.operator === OperatorName.BELONGS) {
          hasConditionErrors = !this.isVariableList(
            _condition.rightOperator.value,
            processVariables,
            dataType
          );
        }

        //constant vs constant
        if (!leftAttributeType && !rightAttributeType) {
          const isRightValueBoolean = isBoolean(_condition.rightOperator.value);
          if (
            (isNaN(Number(_condition.rightOperator.value)) ||
              isRightValueBoolean) &&
            rightAttributeType == null
          ) {
            rightType = Primitives.STRING;

            if (isRightValueBoolean) {
              rightType = Primitives.BOOLEAN;

              if (
                (_condition.rightOperator.value == 0 ||
                  _condition.rightOperator.value == 1) &&
                !isNaN(_condition.leftOperator.value)
              ) {
                rightType = Primitives.NUMBER;
              }
            } else if (isNullOrUndefined(_condition.rightOperator.value)) {
              rightType = null;
            }
          } else {
            rightType = Primitives.NUMBER;
          }

          const isLeftValueBoolean = isBoolean(_condition.leftOperator.value);

          if (
            (isNaN(Number(_condition.leftOperator.value)) ||
              isLeftValueBoolean) &&
            leftAttributeType == null
          ) {
            leftType = Primitives.STRING;

            if (isLeftValueBoolean) {
              leftType = Primitives.BOOLEAN;

              if (
                (_condition.leftOperator.value == 0 ||
                  _condition.leftOperator.value == 1) &&
                rightType == Primitives.NUMBER
              ) {
                leftType = Primitives.NUMBER;
              }
            } else if (isNullOrUndefined(_condition.leftOperator.value)) {
              leftType = null;
            }
          } else {
            leftType = Primitives.NUMBER;
          }

          if (leftType && rightType && leftType !== rightType) {
            hasConditionErrors = true;
          }
        }

        // const vs attribute
        const checkOppostireAttributeType = (
          attributeType: string,
          oppositeAttributeValue: any,
          operator: OperatorName
        ) => {
          if (isNullOrUndefined(oppositeAttributeValue)) {
            return;
          }

          switch (attributeType) {
            case Primitives.BOOLEAN: {
              if (
                [OperatorName.IS_TRUE, OperatorName.IS_FALSE].includes(operator)
              ) {
                // todo: refactor - add operators to enum
                break;
              }
              const oppositeValue =
                typeof oppositeAttributeValue === "string"
                  ? oppositeAttributeValue.trim()
                  : oppositeAttributeValue;
              if (!isBoolean(oppositeValue)) {
                hasConditionErrors = true;
              }
              break;
            }
            case Primitives.FLOAT:
            case Primitives.DOUBLE:
              if (isNaN(Number(oppositeAttributeValue))) {
                hasConditionErrors = true;
              }
              break;

            case Primitives.INTEGER:
              if (!Number.isInteger(Number(oppositeAttributeValue))) {
                hasConditionErrors = true;
              }
              break;

            case Primitives.STRING:
              break;
          }
        };

        if (rightAttributeType && !leftAttributeType) {
          checkOppostireAttributeType(
            rightAttributeType,
            _condition.leftOperator.value,
            _condition.operator
          );
        }

        if (leftAttributeType && !rightAttributeType) {
          checkOppostireAttributeType(
            leftAttributeType,
            _condition.rightOperator.value,
            _condition.operator
          );
        }
      } else {
        const result =
          _condition.value &&
          this.checkConditionsType(
            _condition.value,
            dataType,
            processVariables
          );

        hasConditionErrors = result.hasConditionErrors;
        hasOperatorErrors = result.hasOperatorErrors;
      }
    });

    return { hasConditionErrors, hasOperatorErrors };
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.9 DataStoreDecisionalValidator (extends ConditionalValidator)

`src/modules/ProcessDesigner/Validation/ControlValidators/DataStoreDecisional/DataStoreDecisionalValidator.ts`

```ts
import {
  Node,
  ProcessInputOuputSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";
import { ConditionalValidator } from "../DecisionalAction/ConditionsValidator";
import { FormBuilder, Validators } from "@/utils/ReactiveForm";
import {
  DataStoreDecisionalCondition,
  DataStoreDecisionalOperatorDefinition,
  DataStoreDecisionalOperatorType,
  DataStoreDecisionalRowCondition,
  isDataStoreDecisionalGroup,
} from "@/modules/ProcessDesigner/components/Controls/DataStoreDecisional/DataStoreDecisional.model";
import { getDataStoreDecisionalOperatorByName } from "@/modules/ProcessDesigner/components/Controls/DataStoreDecisional/dataStoreDecisionalOperators";

const message =
  "Action definition incomplete. Please make sure the Where conditions are configured.";

export class DataStoreDecisionalValidator extends ConditionalValidator {
  doRequiredCheck(node: Node, setting: ProcessInputOuputSetting): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value as Array<{
      condition?: DataStoreDecisionalCondition[];
    }>;

    if (!Array.isArray(value) || value.length === 0) {
      return errors;
    }

    const conditions: DataStoreDecisionalCondition[] =
      value[0]?.condition || [];

    if (conditions.length === 0) {
      return errors;
    }

    const form = new FormBuilder();
    this.buildConditionForm(conditions, form);
    form.validate();

    if (form.hasErrors) {
      errors.push({
        text: message,
        badges: AbstractControlValidator.getBadges(
          node,
          ` - ${setting.label}`
        ),
        key: createGuid(),
        actionId: node.id,
      });
    }

    return errors;
  }

  private buildConditionForm(
    conditions: DataStoreDecisionalCondition[],
    form: FormBuilder,
    level = 0,
    parentIndexes: number[] = []
  ) {
    const parentLevels =
      parentIndexes.join("_") + (parentIndexes.length ? "_" : "") + level;

    conditions.forEach((condition: DataStoreDecisionalCondition, i: number) => {
      if (isDataStoreDecisionalGroup(condition)) {
        form.control(
          "group_" + parentLevels + "_" + condition.id,
          condition.value,
          [Validators.required]
        );
        this.buildConditionForm(condition.value, form, level + 1, [
          ...parentIndexes,
          i,
        ]);
        return;
      }

      const row: DataStoreDecisionalRowCondition = condition;

      form.control("operator_" + parentLevels + "_" + row.id, row.operator, [
        Validators.required,
      ]);

      form.control(
        "left_operator_" + parentLevels + "_" + row.id,
        row.leftOperator.value,
        [Validators.required]
      );

      const operator: DataStoreDecisionalOperatorDefinition | null =
        getDataStoreDecisionalOperatorByName(row.operator);
      if (operator?.operatorType !== DataStoreDecisionalOperatorType.UNARY) {
        form.control(
          "right_operator_" + parentLevels + "_" + row.id,
          row.rightOperator?.value,
          [Validators.required]
        );
      }
    });
  }
}
```

### 4.10 DelayDefinitionValidator

`src/modules/ProcessDesigner/Validation/ControlValidators/DelayAction/DelayDefinitionValidator.ts`

```ts
import {
  DelayDefinitionSetting,
  Node,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { DelayType } from "../../../components/Controls/Delay/Delay.model";
import { DELAY_TYPE_SETTING } from "../../../components/PropertiesPanel/Utils/Settings";
import { WarningI } from "../../Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

export class DelayDefinitionValidator extends AbstractControlValidator {
  invalidDelayValueErrorMessage = "Invalid delay value.";

  doRequiredCheck(node: Node, setting: DelayDefinitionSetting): WarningI[] {
    const value = setting.value;
    const errors: WarningI[] = [];

    const settings = this.getAllSettings(node);

    const delayTypeSetting = settings.find((s) => s.id === DELAY_TYPE_SETTING);
    if (delayTypeSetting && delayTypeSetting.value) {
      const delayType = delayTypeSetting.value as DelayType;

      if (
        !value ||
        !value.value ||
        (delayType === DelayType.WAIT_FOR && !value.interval)
      ) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
          key: createGuid(),
          actionId: node.id
        });
      }

      if (value && value.value) {
        const delayValue = value.value;
        if (
          (delayType === DelayType.WAIT_FOR && delayValue < 0) ||
          (delayType === DelayType.WAIT_UNTIL &&
            !this.isValidDelayDate(new Date(delayValue)))
        ) {
          errors.push({
            text: this.invalidDelayValueErrorMessage,
            badges: AbstractControlValidator.getBadges(node, ` - ${setting.label}`),
            key: createGuid(),
            actionId: node.id
          });
        }
      }
    }

    return errors;
  }

  doDataTypeCheck(): WarningI[] {
    return [];
  }

  isValidDelayDate(date: unknown) {
    if (!date || !(date instanceof Date)) {
      return false;
    }

    const now = new Date();

    date.setSeconds(0);
    now.setSeconds(0);

    if (date.toString() === now.toString()) {
      return true;
    }

    return date >= now;
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.11 DocumentMapperValidator (Document Mapper / Data Store Mapper)

`src/modules/ProcessDesigner/Validation/ControlValidators/DocumentMapper/DocumentMapperValidator.ts`
(`doDataTypeCheck` is currently a commented-out block returning `[]`.)

```ts
import {
  Node,
  DocumentMapperSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";
import { store } from "@/store";
import { DocumentMapperValue } from "@/modules/ProcessDesigner/components/Controls/DocumentMapper/DocumentMapper.model";
import { Variable } from "@/services/crud/Orchestration.service";
import { hasVariable } from "@/modules/ProcessDesigner/Variables/Utils";

export class DocumentMapperValidator extends AbstractControlValidator {
  requiredVariableCheckErrorMessage =
    "Please make sure that all document varibles are mapped.";

  doRequiredCheck(node: Node, setting: DocumentMapperSetting): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value;
    if (!value || (Array.isArray(value) && value.length === 0)) {
      return errors;
    }

    value
      .filter(
        (row) => !row.document || (row.document && hasVariable(row.document))
      )
      .forEach((row, rowIndex) => {
        if (!row.document || row.document.trim().length === 0) {
          errors.push({
            text: this.requiredCheckErrorMessage,
            badges: AbstractControlValidator.getBadges(
              node,
              ` - ${setting.label} (row ${rowIndex + 1})`
            ),
            key: createGuid(),
            actionId: node.id,
          });
        }
      });

    return errors;
  }

  doDataTypeCheck(): WarningI[] {
    return [];
    // ... (data-type check currently commented out)
  }

  checkRequiredVariablesMapping(
    node: Node,
    setting: DocumentMapperSetting
  ): WarningI[] {
    const variables = store.getters.getExtraVariablesByNodeId(node.id);
    const value: DocumentMapperValue[] = setting.value;

    const errors: WarningI[] = [];

    variables.forEach((v: Variable) => {
      // if document variable is not mapped
      if (
        !Array.isArray(value) ||
        value.findIndex((mv) => mv.document === v.id) === -1
      ) {
        errors.push({
          text: this.requiredVariableCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (${v.name})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.12 ColumnDefinitionControlValidator (Get File Data)

`src/modules/ProcessDesigner/Validation/ControlValidators/GetFileData/ColumnDefinitionControlValidator.ts`

```ts
import {
  ColumnDefinitionSetting,
  Node,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { Primitives } from "@/utils/dataTypeMapper";
import { getValueDataTypes } from "../../../Values/ValueDataTypesHelper";
import { SettingValidation } from "../../SettingValidation";
import { WarningI } from "../../Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

export class ColumnDefinitionControlValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: ColumnDefinitionSetting): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value;
    const rows = value ? value.rows : null;

    if (!rows || (Array.isArray(rows) && rows.length === 0)) {
      errors.push({
        text: this.requiredCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(
          node,
          ` - column definition`
        ),
        key: createGuid(),
        actionId: node.id,
      });
      return errors;
    }

    rows.forEach((row, rowIndex) => {
      if (
        !row.columnName ||
        row.columnName.trim().length === 0 ||
        !row.attribute ||
        row.attribute.trim().length === 0
      ) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (row ${rowIndex + 1})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doDataTypeCheck(node: Node, setting: ColumnDefinitionSetting): WarningI[] {
    const errors: WarningI[] = [];

    setting.dataTypeId = Primitives.STRING;

    const value = setting.value;
    const rows = value ? value.rows : null;

    if (!rows || (Array.isArray(rows) && rows.length === 0)) {
      return [];
    }

    rows.forEach((row, rowIndex) => {
      const attributeValue = row.attribute ? row.attribute.trim() : "";
      if (
        !SettingValidation.validateDataType(
          getValueDataTypes(attributeValue),
          setting
        )
      ) {
        errors.push({
          text: this.typeCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} attribute (row ${rowIndex + 1})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.13 MapParametersValidator

`src/modules/ProcessDesigner/Validation/ControlValidators/MapParameters/MapParametersValidator.ts`

```ts
import {
  Node,
  MapParametersSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";

export class MapParametersValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: MapParametersSetting): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value;

    if (Array.isArray(value) && value.length === 0) {
      return [];
    }

    if (!value) {
      errors.push({
        text: this.requiredCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(
          node,
          ` - ${setting.label} (row 1)`
        ),
        key: createGuid(),
        actionId: node.id,
      });

      return errors;
    }

    value.forEach((row, rowIndex) => {
      if (!row.destination || row.source.trim().length === 0) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (row ${rowIndex + 1})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doDataTypeCheck(node: Node, setting: MapParametersSetting): WarningI[] {
    return [];
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

### 4.14 MapProcessDataValidator

`src/modules/ProcessDesigner/Validation/ControlValidators/MapProcessData/MapProcessDataValidator.ts`

```ts
import {
  Node,
  MapProcessDataSetting,
} from "@/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model";
import { createGuid } from "@/utils/type/guid";
import { WarningI } from "@/modules/ProcessDesigner/Validation/Validation";
import { AbstractControlValidator } from "../AbstractControlValidator";
import {
  isCustomTypeAllowed,
  NonPrimitives,
  Primitives,
} from "@/utils/dataTypeMapper";
import { SettingValidation } from "../../SettingValidation";
import { getValueDataTypes } from "@/modules/ProcessDesigner/Values/ValueDataTypesHelper";
import {
  DataModel,
  isCustomDataModel,
} from "@/services/datamodel/DataModel.model";
import cloneDeep from "lodash/cloneDeep";

export class MapProcessDataValidator extends AbstractControlValidator {
  doRequiredCheck(node: Node, setting: MapProcessDataSetting): WarningI[] {
    const errors: WarningI[] = [];

    const value = setting.value;

    if (Array.isArray(value) && value.length === 0) {
      return [];
    }

    if (!value) {
      errors.push({
        text: this.requiredCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(
          node,
          ` - ${setting.label} (row 1)`
        ),
        key: createGuid(),
        actionId: node.id,
      });

      return errors;
    }

    value.forEach((row, rowIndex) => {
      if (!row.destination || row.source.trim().length === 0) {
        errors.push({
          text: this.requiredCheckErrorMessage,
          badges: AbstractControlValidator.getBadges(
            node,
            ` - ${setting.label} (row ${rowIndex + 1})`
          ),
          key: createGuid(),
          actionId: node.id,
        });
      }
    });

    return errors;
  }

  doDataTypeCheck(node: Node, setting: MapProcessDataSetting): WarningI[] {
    setting = cloneDeep(setting);

    const value = setting.value;

    if (!value || value.length === 0) {
      return [];
    }

    const errors: WarningI[] = [];
    const addTypeCheckError = (rowIndex: number) => {
      errors.push({
        text: this.typeCheckErrorMessage,
        badges: AbstractControlValidator.getBadges(
          node,
          ` - ${setting.label} (row ${rowIndex + 1})`
        ),
        key: createGuid(),
        actionId: node.id,
      });
    };

    const originalSettingDataTypeId = setting.dataTypeId;
    const originalSettingIsListState = setting.isList;

    value.forEach((row, rowIndex) => {
      const destinationValue = row.destination;
      const descriptionValueTypesGrouped = getValueDataTypes(destinationValue);

      // check if source and destination variables have same type
      const checkDataTypes = (types: DataModel[], isList = false) => {
        if (types.length > 0) {
          const destinationValueType = types[0];
          // if destination is a string, make it accept ANY data type
          let dataTypeId = destinationValueType.id;

          const sourceValueTypesGrouped = getValueDataTypes(row.source);

          // allow map any value to string
          // allow map json to custom data model
          if (
            destinationValueType.id === Primitives.STRING ||
            (isCustomDataModel(destinationValueType) &&
              (isCustomTypeAllowed(sourceValueTypesGrouped.scalar[0]?.id) ||
                isCustomTypeAllowed(sourceValueTypesGrouped.list[0]?.id)))
          ) {
            dataTypeId = NonPrimitives.OBJECT;
          }

          setting.dataTypeId = dataTypeId;
          setting.isList = isList;

          // allow mapping File to File and File[] to File[]; PRC-3272
          const isMappingFileToFile =
            dataTypeId === NonPrimitives.FILE &&
            ((!isList &&
              sourceValueTypesGrouped.scalar.length === 1 &&
              sourceValueTypesGrouped.scalar[0].id === NonPrimitives.FILE) ||
              (isList &&
                sourceValueTypesGrouped.list.length === 1 &&
                sourceValueTypesGrouped.list[0].id === NonPrimitives.FILE));

          if (
            !isMappingFileToFile &&
            !SettingValidation.validateDataType(
              sourceValueTypesGrouped,
              setting,
              // file is not allowed
              [NonPrimitives.FILE]
            )
          ) {
            addTypeCheckError(rowIndex);
          }
        }
      };

      checkDataTypes(descriptionValueTypesGrouped.scalar);
      checkDataTypes(descriptionValueTypesGrouped.list, true);

      // reset setting props to original state
      setting.dataTypeId = originalSettingDataTypeId;
      setting.isList = originalSettingIsListState;
    });

    return errors;
  }

  doValueCheck(): WarningI[] {
    return [];
    //todo
  }
}
```

---

## 5. DecisionalCard.validation.ts (used by ConditionalValidator)

`src/modules/ProcessDesigner/components/Controls/DecisionalManager/card/DecisionalCard.validation.ts`

```ts
import {
  Operator,
  OperatorType,
} from "@/services/actionlist/ActionList.service";
import { store } from "@/store";
import { FormBuilder, Validators } from "@/utils/ReactiveForm";
import { Condition, RowCondition } from "../Decisional.model";

interface DecisionalCardValue {
  id: string;
  name: string;
  target: string;
  condition: Condition[];
}

const buildForm = (
  conditions: Condition[],
  form: FormBuilder,
  level = 0,
  parentIndexes: number[] = []
) => {
  const parentLevels =
    parentIndexes.join("_") + (parentIndexes.length ? "_" : "") + level;

  conditions.forEach((condition: Condition, i: number) => {
    if (!("value" in condition) || condition.value === null) {
      condition = condition as RowCondition;

      form.control(
        "operator_" + parentLevels + "_" + condition.id,
        condition.operator,
        [Validators.required]
      );

      form.control(
        "left_operator_" + parentLevels + "_" + condition.id,
        condition.leftOperator.value,
        [Validators.required]
      );

      const operator: Operator | null = store.getters.getConditionOperandByName(
        condition.operator
      );
      if (operator?.operatorType !== OperatorType.UNARY) {
        form.control(
          "right_operator_" + parentLevels + "_" + condition.id,
          condition.rightOperator?.value,
          [Validators.required]
        );
      }

      if (condition.auxOperator) {
        form.control(
          "aux_operator_" + parentLevels + "_" + condition.id,
          condition.auxOperator.value,
          []
        );
      }
    } else if (Array.isArray(condition.value)) {
      form.control(
        "group_" + parentLevels + "_" + condition.id,
        condition.value,
        [Validators.required]
      );
      return buildForm(condition.value, form, ++level, [...parentIndexes, i]);
    }
  });
};

const DecisionalCardValidation = (value: DecisionalCardValue) => {
  const form = new FormBuilder();

  form.control("name", value.name, [
    Validators.required,
    Validators.minLength(1),
  ]);
  form.control("target", value.target, [Validators.required]);

  form.control("conditions", value.condition.length, [Validators.min(1)]);

  buildForm(value.condition, form);

  form.validate();

  return form.hasErrors;
};

export default DecisionalCardValidation;
```

---

## 6. Constant reference (values)

The validation code above references template IDs, setting IDs, data-type GUIDs,
and enums by name. Their actual values are listed here.

### 6.1 Action template IDs

`src/utils/actionHelper.ts`

```ts
export const START_ACTION_TEMPLATE_ID     = "c0e32108-6e3e-4ab8-96bd-cd61be6edb33";
export const STOP_ACTION_TEMPLATE_ID      = "c0e32108-6e3e-4ab8-96bd-cd61be6edb34";
export const JOIN_TEMPLATE_ID             = "fb6a9d14-dd15-420d-a2b2-fc637c0c37c6";
export const FOREACH_TEMPLATE_ID          = "dbef0804-66a9-4f8f-872c-ece1b89b8fdb";
export const CALL_SUBPROCESS_TEMPLATE_ID  = "c37e56fe-d924-4604-a86f-7c93f863fcdf";
export const TRIGGER_SUBPROCESS_TEMPLATE_ID = "615365f9-9ccb-dd46-85a6-af824b7be897";
export const GENERATE_DOCUMENT_TEMPLATE_ID  = "cdae0149-ab39-4d07-a72f-549c64cd10fe";
export const DECISIONAL_TEMPLATE_ID       = "f5dcbb04-253d-4061-99a1-9b2822c2e6d2";
export const AI_DECISIONAL_TEMPLATE_ID    = "772aac51-73f5-471d-bf9f-f5099cb30001";
```

> Note: `checkPointsValidation` in `Validation.ts` hard-codes the start/stop GUIDs
> as string literals (`"c0e32108-...edb33"` / `"...edb34"`) instead of importing the
> constants above — same values.

### 6.2 Setting IDs

`src/modules/ProcessDesigner/components/PropertiesPanel/Utils/Settings.ts`

```ts
// Call Subprocess action
export const SUBPROCESS_SELECT_SETTING          = "bc93d0be-98f6-42d6-b2ac-a782eadd79bf";
export const SUBPROCESS_SIDE_PANEL_SETTING      = "5456caf0-be8e-4a04-86cb-dbae203af978";
// Trigger Subprocess action
export const TRIGGER_SUBPROCESS_SELECT_SETTING     = "6824ee16-b6c4-a34e-bd21-f8136346af81";
export const TRIGGER_SUBPROCESS_SIDE_PANEL_SETTING = "8540605e-2f4d-1746-9059-8bb7b944e0d3";
// Delay action
export const DELAY_TYPE_SETTING       = "f1293589-6ede-4cc6-a04b-cc70e7084cb0";
// Decisional
export const DECISIONAL_CASE_SETTING    = "11d4044a-8586-47f6-b3ce-1cae5da40f30";
export const AI_DECISIONAL_CASE_SETTING = "772aac51-73f5-471d-bf9f-f5099cb30124";
```

### 6.3 Data-type GUIDs — Primitives / NonPrimitives

`src/utils/dataTypeMapper.ts`

```ts
export enum Primitives {
  BOOLEAN      = "0317bfee-b2f5-4bde-bfe8-121212121210",
  INTEGER      = "0317bfee-b2f5-4bde-bfe8-121212121211",
  FLOAT        = "0317bfee-b2f5-4bde-bfe8-121212121212",
  DOUBLE       = "0317bfee-b2f5-4bde-bfe8-121212121213",
  STRING       = "0317bfee-b2f5-4bde-bfe8-121212121214",
  DATE         = "0317bfee-b2f5-4bde-bfe8-121212121215",
  RELATIONSHIP = "0317bfee-b2f5-4bde-bfe8-121212121216",
  TIME         = "0317bfee-b2f5-4bde-bfe8-121212121217",
  DATETIME     = "0317bfee-b2f5-4bde-bfe8-121212121218",
  NUMBER       = "NUMBER",
  GUID         = "0317bfee-b2f5-4bde-bfe8-121212121222",
}

export enum NonPrimitives {
  FILE            = "10c6ac59-3929-49e6-99dc-121212121219",
  JSON            = "0317bfee-b2f5-4bde-bfe8-121212121220",
  OBJECT          = "0317bfee-b2f5-4bde-bfe8-121212121221",
  SYSTEM_VARIABLE = "10c6ac59-3929-49e6-99dc-121212121221",
  ERROR           = "10c6ac59-3929-49e6-99dc-121212121220",
  FUNCTION        = "1c2fd144-836e-419a-aa25-9e624a4c7e40",
}

// helpers used by SettingValidation.validateDataType
export const isPrimitive = (dataTypeId: string) =>
  (Object.values(Primitives) as string[]).includes(dataTypeId);

// only JSON and OBJECT accept an arbitrary custom data model
export const isCustomTypeAllowed = (dataTypeId: string) =>
  ([NonPrimitives.JSON, NonPrimitives.OBJECT] as string[]).includes(dataTypeId);
```

### 6.4 SettingType values (drives ControlValidatorFactory)

`src/modules/ProcessDesigner/components/PropertiesPanel/PropertiesPanel.model.ts`

```ts
export enum SettingType {
  TABS_PAYLOAD_OLD       = "tabs-payload",       // todo: delete after tabs payload v2
  TABS_PAYLOAD           = "tabs-payload-v2",
  DECISIONAL_CASE        = "decisional-case",
  AI_DECISIONAL_CASE     = "ai-decisional-case",
  PROCESS_INPUT          = "process-inputs",
  PROCESS_OUTPUT         = "process-outputs",
  COLUMN_DEFINITION      = "column-definition",
  DELAY_DEFINITION       = "delay-definition",
  MAP_PROCESS_DATA       = "map-process-data",
  DOCUMENT_MAPPER_BUILDER = "document-mapper",
  DATA_STORE_MAPPER      = "data-store-mapper",
  DATA_STORE_DECISIONAL  = "data-store-decisional",
  NUMBER                 = "number",
  MAP_PARAMETERS         = "map-parameters",
  // ...other SettingType members exist but are not referenced by the validators
}
```
