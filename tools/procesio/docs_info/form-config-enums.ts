// PROCESIO FormBuilder config enums — AUTHORITATIVE source of the string values that
// `FormBuilder mock.ts` references via ElementConfigType.X / ElementConfigSubCategory.X /
// ElementConfigCategory.X / ElementConfigEvent.X (the mock imports these from "../config").
//
// Provided verbatim by the frontend team (2026-06-25). sync_from_mock.py parses this file
// directly, so every enum member resolves authoritatively — no guessing, ever.
// When the frontend adds/changes a control config type, update THIS file (paste the new
// enum) and re-run `python sync_from_mock.py --write`.

export enum ElementConfigCategory {
  CONTENT = "content",
  STYLING = "styling",
}

export enum ElementConfigSubCategory {
  GENERAL = "general",
  CONTOLS = "controls", // note: member name misspelled, value is "controls"
  VALIDATION = "validation",
  DATA_SOURCE = "data-source",
  TASK_ASSIGNEE = "task-assignee",
  APPROVALS = "approvals",
  RULES = "rules",
  ADD_RULES = "add-rules",
  ACTION = "action",
  EVENTS = "events",
  ASSIGNMENT_CONFIG = "assignment-config",
}

export enum ElementConfigType {
  INPUT = "input",
  TEXTAREA = "textarea",
  NUMBER_INPUT = "number-input",
  COPYABLE_INPUT = "copyable-input",
  DATETIME_DEFAULT_VALUE = "datetime-default-value",
  DATETIME_MIN_MAX_VALUE = "datetime-min-max-value",
  DATE_TIME_INTERVALS = "date-time-intervals",
  ELEMENT_ATTRIBUTES = "element-attributes",
  TOGGLE = "toggle",
  SELECT = "select",
  CLEARABLE_SELECT = "clearable-select",
  USER_SELECT = "user-select",
  CHECKBOX = "checkbox",
  RADIOBOX = "radiobox",
  ASSIGNEE_REPLACEMENT = "assignee-replacement",
  APPROVER_REPLACEMENT = "approver-replacement",
  RULES_VISIBILITY = "rules-visibility",
  JS_CODE_EDITOR = "js-code-editor",
  HTML_CODE_EDITOR = "html-code-editor",
  SOURCE_TYPE = "source-type",
  TABLE_COLUMNS_SOURCE_TYPE = "table-columns-source-type",
  CHART_CATEGORIES_SOURCE_TYPE = "chart-categories-source-type",
  CHART_SERIES_SOURCE_TYPE = "chart-series-source-type",
  SOURCE_VALUE = "source-value",
  TABLE_COLUMNS_SOURCE_VALUE = "table-columns-source-value",
  CHART_CATEGORIES_SOURCE_VALUE = "chart-categories-source-value",
  CHART_SERIES_SOURCE_VALUE = "chart-series-source-value",
  COLUMN_LIST = "column-list",
  STEP_LIST = "step-list",
  TAB_LIST = "tab-list",
  HIDDEN = "hidden",
  TEMPLATE_ONLY = "template-only",
  UPLOAD_FILE_TYPE_SELECT = "upload-file-type-select",
  VIEW_FILE_TYPE_SELECT = "view-file-type-select",
  VIEWER_TYPE_RADIO = "viewer-type-radio",
  FIELD_EVENTS = "field-events",
  BUTTON_SUBMIT_TOGGLE = "button-submit-toggle",
  DATE_TIME_MODE_SELECT = "date-time-mode-select",
  CSS_VARIABLE_SELECT = "css-variable-select",
  CSS_COLOR_PREVIEW = "css-color-preview",
  URL_OR_FILE = "url-or-file",
  URL_TARGET_SELECT = "url-target-select",
  ROW_LIST = "row-list",
  ROW_CELL_APPROVALS = "row-cell-approvals",
  TABLE_PAGINATION = "table-pagination",
  ICON_PICKER = "icon-picker",
  OPEN_SIDE_PANEL_BUTTON = "open-side-panel-button",
  INPUT_TYPE_SELECT = "input-type-select",
  ASSIGNMENT_CONFIG = "assignment-config",
  ASSIGNMENT_FORM_TYPE = "assignment-form-type",
  ASSIGNMENT_FORM_SELECT = "assignment-form-select",
  ASSIGNMENT_ELEMENT_SELECT = "assignment-element-select",
  READONLY_OR_DISABLED_TOGGLE = "readonly-or-disabled",
  REQUIRED_COMMENT = "required-comment",
  DROPDOWN_ITEMS = "dropdown-items",
  FUNCTION = "function",
}

export enum ElementConfigEvent {
  EMIT_INPUT = "EMIT_INPUT",
  REMAP = "REMAP",
  EMIT_ELEMENTS_UPDATE = "EMIT_ELEMENTS_UPDATE",
}
