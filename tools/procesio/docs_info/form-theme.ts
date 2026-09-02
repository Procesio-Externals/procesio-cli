import { ElementConfigType } from ".";
import { ElementType } from "../element";

export type Theme = CSSPropertyGroup[];

export interface CSSPropertyGroup {
  label: CSSGroups;
  types: ElementType[] | null;
  properties: CSSProperty[];
}

export interface CSSProperty {
  label: string;
  value: string;
  cssVariable: string;
  type?: ElementConfigType;
  group?: CSSGroups;
  isEditable?: boolean;
  enabled?: boolean;
}

export enum CSSGroups {
  COLORS = "Colors",
  FONTS = "Fonts",
  FORM = "Form",
  INPUT = "Input",
  SELECT = "Select",
  BUTTON = "Button",
  CHECKBOX = "Checkbox",
  RADIOBOX = "Radiobox",
  APPROVAL = "Approval",
  FILE_UPLOAD = "File Upload",
  SECTION = "Section",
  LIST = "List",
  TABLE = "Table",
  COLUMNS = "Columns",
  STEPPER = "Stepper",
  TABS = "Tabs",
  SIDE_PANEL = "Side Panel",
  ICON = "Icon",
  DROPDOWN = "Dropdown",
  TEST = "Test",
}

export const getDefaultTheme = (): CSSPropertyGroup[] => [
  {
    label: CSSGroups.COLORS,
    types: null,
    properties: [
      {
        label: "Primary",
        value: "#0039e3",
        cssVariable: "--c-primary",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Primary Variant",
        value: "#2a64ff",
        cssVariable: "--c-primary-variant",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "On Primary",
        value: "#f7f9fc",
        cssVariable: "--c-on-primary",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Error",
        value: "#f42727",
        cssVariable: "--c-error",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "On Error",
        value: "#f2f5fa",
        cssVariable: "--c-on-error",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Success",
        value: "#409920",
        cssVariable: "--c-success",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "On Success",
        value: "#f2f5fa",
        cssVariable: "--c-on-success",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Info",
        value: "#0671d6",
        cssVariable: "--c-info",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 900",
        value: "#0f1427",
        cssVariable: "--c-neutral--900",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 800",
        value: "#141a32",
        cssVariable: "--c-neutral--800",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 700",
        value: "#202b47",
        cssVariable: "--c-neutral--700",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 600",
        value: "#2c3a5c",
        cssVariable: "--c-neutral--600",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 500",
        value: "#8d9bb5",
        cssVariable: "--c-neutral--500",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 400",
        value: "#c3cee2",
        cssVariable: "--c-neutral--400",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 300",
        value: "#e3e8f3",
        cssVariable: "--c-neutral--300",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 200",
        value: "#ecf1f8",
        cssVariable: "--c-neutral--200",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 100",
        value: "#f2f5fa",
        cssVariable: "--c-neutral--100",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "Neutral 50",
        value: "#f7f9fc",
        cssVariable: "--c-neutral--50",
        type: ElementConfigType.CSS_COLOR_PREVIEW,
      },
      {
        label: "White",
        value: "#fff",
        cssVariable: "--c-white",
        isEditable: false,
      },
      {
        label: "Transparent",
        value: "transparent",
        cssVariable: "--c-transparent",
        isEditable: false,
      },
    ],
  },
  {
    label: CSSGroups.FONTS,
    types: null,
    properties: [
      {
        label: "Input font size",
        value: "14px",
        cssVariable: "--fs-input",
      },
      {
        label: "Input line height",
        value: "20px",
        cssVariable: "--lh-input",
      },
      {
        label: "Label font size",
        value: "12px",
        cssVariable: "--fs-label",
      },
      {
        label: "Label line height",
        value: "16px",
        cssVariable: "--lh-label",
      },
      {
        label: "Button font size",
        value: "16px",
        cssVariable: "--fs-button",
      },
      {
        label: "Heading font size",
        value: "21px",
        cssVariable: "--fs-heading",
      },
      {
        label: "Heading line height",
        value: "25px",
        cssVariable: "--lh-heading",
      },
      {
        label: "Paragraph font size",
        value: "15px",
        cssVariable: "--fs-paragraph",
      },
      {
        label: "Paragraph line height",
        value: "22px",
        cssVariable: "--lh-paragraph",
      },
    ],
  },
  {
    label: CSSGroups.FORM,
    types: null,
    properties: [
      {
        label: "Background color",
        value: "--c-neutral--50",
        cssVariable: "--c-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Surface color",
        value: "--c-white",
        cssVariable: "--c-surface",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Padding",
        value: "16px",
        cssVariable: "--p-form",
      },
      {
        label: "Gap",
        value: "20px",
        cssVariable: "--gap",
      },
      {
        label: "Link color",
        value: "--c-primary",
        cssVariable: "--c-link",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Link decoration",
        value: "none",
        cssVariable: "--d-link",
      },
      {
        label: "Heading color",
        value: "--c-neutral--800",
        cssVariable: "--c-heading",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Paragraph color",
        value: "--c-neutral--800",
        cssVariable: "--c-paragraph",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.INPUT,
    types: [
      ElementType.INPUT,
      ElementType.NUMBER_INPUT,
      ElementType.DATETIME_INPUT,
      ElementType.TEXTAREA,
      ElementType.SELECT,
    ],
    properties: [
      {
        label: "Width",
        value: "inherit",
        cssVariable: "--w-input",
      },
      {
        label: "Height",
        value: "40px",
        cssVariable: "--h-input",
      },
      {
        label: "Padding vertical",
        value: "10px",
        cssVariable: "--pv-input",
      },
      {
        label: "Padding horizontal",
        value: "8px",
        cssVariable: "--ph-input",
      },
      {
        label: "Label color",
        value: "--c-neutral--800",
        cssVariable: "--c-label",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Input color",
        value: "--c-neutral--800",
        cssVariable: "--c-input-value",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Placeholder color",
        value: "--c-neutral--500",
        cssVariable: "--c-input-placeholder",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color",
        value: "--c-neutral--50",
        cssVariable: "--c-input-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color hover",
        value: "--c-neutral--100",
        cssVariable: "--c-input-background--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Alternative background color",
        value: "--c-white",
        cssVariable: "--c-input-background-alt",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Alternative background color hover",
        value: "--c-neutral--50",
        cssVariable: "--c-input-background-alt--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border radius",
        value: "4px",
        cssVariable: "--br-input",
      },
      {
        label: "Border width",
        value: "1px",
        cssVariable: "--bw-input",
      },
      {
        label: "Border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-input",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color focused",
        value: "--c-primary",
        cssVariable: "--bc-input-focused",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color error",
        value: "--c-error",
        cssVariable: "--bc-input-error",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Outline width",
        value: "4px",
        cssVariable: "--w-outline",
      },
      {
        label: "Input color disabled",
        value: "--c-neutral--800",
        cssVariable: "--c-input-value-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color disabled",
        value: "--c-neutral--50",
        cssVariable: "--c-input-background-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color disabled",
        value: "--c-neutral--300",
        cssVariable: "--bc-input-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.SELECT,
    types: [ElementType.SELECT],
    properties: [
      {
        label: "Dropdown background color",
        value: "--c-white",
        cssVariable: "--c-select-dropdown-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown options gap",
        value: "0px",
        cssVariable: "--gap-select-dropdown",
      },
      {
        label: "Dropdown padding vertical",
        value: "8px",
        cssVariable: "--pv-select-dropdown",
      },
      {
        label: "Dropdown padding horizontal",
        value: "8px",
        cssVariable: "--ph-select-dropdown",
      },
      {
        label: "Option background color",
        value: "--c-transparent",
        cssVariable: "--c-option-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option hover background color",
        value: "--c-neutral--100",
        cssVariable: "--c-option-background--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option selected background color",
        value: "--c-neutral--200",
        cssVariable: "--c-option-background--selected",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option text color",
        value: "--c-neutral--800",
        cssVariable: "--c-option-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option hover text color",
        value: "--c-neutral--800",
        cssVariable: "--c-option--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option selected text color",
        value: "--c-primary",
        cssVariable: "--c-option-text--selected",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option padding vertical",
        value: "8px",
        cssVariable: "--pv-option",
      },
      {
        label: "Option padding horizontal",
        value: "8px",
        cssVariable: "--ph-option",
      },
      {
        label: "Option border radius",
        value: "4px",
        cssVariable: "--br-option",
      },
    ],
  },
  {
    label: CSSGroups.BUTTON,
    types: [ElementType.BUTTON],
    properties: [
      {
        label: "Label color",
        value: "--c-on-primary",
        cssVariable: "--c-btn-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color",
        value: "--c-primary",
        cssVariable: "--c-btn-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color hover",
        value: "--c-primary-variant",
        cssVariable: "--c-btn-background--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Width",
        value: "inherit",
        cssVariable: "--w-btn",
      },
      {
        label: "Height",
        value: "40px",
        cssVariable: "--h-btn",
      },
      {
        label: "Padding vertical",
        value: "8px",
        cssVariable: "--pv-btn",
      },
      {
        label: "Padding horizontal",
        value: "12px",
        cssVariable: "--ph-btn",
      },
      {
        label: "Border radius",
        value: "4px",
        cssVariable: "--br-btn",
      },
      {
        label: "Border width",
        value: "1px",
        cssVariable: "--bw-btn",
      },
    ],
  },
  {
    label: CSSGroups.CHECKBOX,
    types: [ElementType.CHECKBOX],
    properties: [
      {
        label: "Width",
        value: "10px",
        cssVariable: "--w-checkbox",
      },
      {
        label: "Height",
        value: "10px",
        cssVariable: "--h-checkbox",
      },
      {
        label: "Background color",
        value: "--c-neutral--100",
        cssVariable: "--c-checkbox-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color disabled",
        value: "--c-neutral--400",
        cssVariable: "--c-checkbox-background-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color checked",
        value: "--c-primary",
        cssVariable: "--c-checkbox-background-checked",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color checked disabled",
        value: "--c-neutral--500",
        cssVariable: "--c-checkbox-background-checked-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border radius",
        value: "2px",
        cssVariable: "--br-checkbox",
      },
      {
        label: "Border width",
        value: "2px",
        cssVariable: "--bw-checkbox",
      },
      {
        label: "Border color",
        value: "--c-neutral--400",
        cssVariable: "--bc-checkbox",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color disabled",
        value: "--c-neutral--400",
        cssVariable: "--bc-checkbox-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color checked disabled",
        value: "--c-neutral--500",
        cssVariable: "--bc-checkbox-checked-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color checked",
        value: "--c-primary",
        cssVariable: "--bc-checkbox-checked",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.RADIOBOX,
    types: [ElementType.RADIOBOX],
    properties: [
      {
        label: "Width",
        value: "14px",
        cssVariable: "--w-radiobox",
      },
      {
        label: "Height",
        value: "14px",
        cssVariable: "--h-radiobox",
      },
      {
        label: "Background color",
        value: "--c-neutral--100",
        cssVariable: "--c-radiobox-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color checked",
        value: "--c-primary",
        cssVariable: "--c-radiobox-background-checked",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color checked disabled",
        value: "--c-neutral--100",
        cssVariable: "--c-radiobox-background-checked-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border radius",
        value: "50%",
        cssVariable: "--br-radiobox",
      },
      {
        label: "Border width",
        value: "2px",
        cssVariable: "--bw-radiobox",
      },
      {
        label: "Border color",
        value: "--c-neutral--400",
        cssVariable: "--bc-radiobox",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color disabled",
        value: "--c-neutral--400",
        cssVariable: "--bc-radiobox-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color checked",
        value: "--c-primary",
        cssVariable: "--bc-radiobox-checked",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border color checked disabled",
        value: "--c-neutral--500",
        cssVariable: "--bc-radiobox-checked-disabled",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Option label color",
        value: "--c-neutral--800",
        cssVariable: "--c-radiobox-option",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      }
    ],
  },
  {
    label: CSSGroups.APPROVAL,
    types: [ElementType.APPROVAL],
    properties: [
      {
        label: "Header background color",
        value: "--c-neutral--100",
        cssVariable: "--c-approval-header--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Surface background color",
        value: "--c-white",
        cssVariable: "--c-approval-body--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Surface border radius",
        value: "4px",
        cssVariable: "--br-approval-surface",
      },
      {
        label: "Surface border width",
        value: "1px",
        cssVariable: "--bw-approval-surface",
      },
      {
        label: "Surface border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-approval-surface",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Buttons width",
        value: "88px",
        cssVariable: "--w-btn-approval",
      },
      {
        label: "Buttons height",
        value: "40px",
        cssVariable: "--h-btn-approval",
      },
      {
        label: "Buttons padding vertical",
        value: "8px",
        cssVariable: "--pv-btn-approval",
      },
      {
        label: "Buttons padding horizontal",
        value: "12px",
        cssVariable: "--ph-btn-approval",
      },
      {
        label: "Buttons border radius",
        value: "4px",
        cssVariable: "--br-btn-approval",
      },
      {
        label: "Buttons border width",
        value: "1px",
        cssVariable: "--bw-btn-approval",
      },
      {
        label: "Button approve background color",
        value: "--c-success",
        cssVariable: "--c-btn-approve--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button approve text color",
        value: "--c-on-success",
        cssVariable: "--c-btn-approve--text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button reject background color",
        value: "--c-error",
        cssVariable: "--c-btn-reject--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button reject text color",
        value: "--c-on-error",
        cssVariable: "--c-btn-reject--text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.FILE_UPLOAD,
    types: [ElementType.FILE_UPLOAD],
    properties: [
      {
        label: "Theme color",
        value: "--c-primary",
        cssVariable: "--c-upload-theme-color",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button background color",
        value: "--c-primary",
        cssVariable: "--c-upload-btn--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button text color",
        value: "--c-on-primary",
        cssVariable: "--c-upload-btn--text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },

  {
    label: CSSGroups.SECTION,
    types: [ElementType.SECTION],
    properties: [
      {
        label: "Label color",
        value: "--c-neutral--800",
        cssVariable: "--c-section-label",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Width",
        value: "100%",
        cssVariable: "--w-section",
      },
      {
        label: "Height",
        value: "inherit",
        cssVariable: "--h-section",
      },
      {
        label: "Gap",
        value: "10px",
        cssVariable: "--gap-section",
      },
      {
        label: "Padding vertical",
        value: "16px",
        cssVariable: "--pv-section",
      },
      {
        label: "Padding horizontal",
        value: "16px",
        cssVariable: "--ph-section",
      },
      {
        label: "Background color",
        value: "--c-neutral--50",
        cssVariable: "--c-section-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border radius",
        value: "4px",
        cssVariable: "--br-section",
      },
      {
        label: "Border width",
        value: "1px",
        cssVariable: "--bw-section",
      },
      {
        label: "Border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-section",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  /**
   * Add new group List with the following properties
   *  --w-list-surface: 100%;
    --h-list-surface: inherit;

    --gap-list-surface: 16px;

    --pv-list-surface: 16px;
    --ph-list-surface: 16px;

    --c-list-surface--background: var(--c-white);

    --br-list-surface: 4px;
    --bw-list-surface: 1px;
    --bc-list-surface: var(--c-neutral--300);

    --w-list-item: 100%;
    --h-list-item: inherit;

    --gap-list-item: 16px;

    --pv-list-item: 16px;
    --ph-list-item: 16px;

    --c-list-item-background: var(--c-neutral--50);

    --br-list-item: 4px;
    --bw-list-item: 1px;
    --bc-list-item: var(--c-neutral--100);

    --c--list-add--background: var(--c-primary);
    --c--list-add--text: var(--c-on-primary);
   */
  {
    label: CSSGroups.LIST,
    types: [ElementType.LIST],
    properties: [
      {
        label: "Surface width",
        value: "100%",
        cssVariable: "--w-list-surface",
      },
      {
        label: "Surface height",
        value: "inherit",
        cssVariable: "--h-list-surface",
      },
      {
        label: "Surface gap",
        value: "16px",
        cssVariable: "--gap-list-surface",
      },
      {
        label: "Surface padding vertical",
        value: "16px",
        cssVariable: "--pv-list-surface",
      },
      {
        label: "Surface padding horizontal",
        value: "16px",
        cssVariable: "--ph-list-surface",
      },
      {
        label: "Surface background color",
        value: "--c-white",
        cssVariable: "--c-list-surface--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Surface border radius",
        value: "4px",
        cssVariable: "--br-list-surface",
      },
      {
        label: "Surface border width",
        value: "1px",
        cssVariable: "--bw-list-surface",
      },
      {
        label: "Surface border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-list-surface",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Item width",
        value: "100%",
        cssVariable: "--w-list-item",
      },
      {
        label: "Item height",
        value: "inherit",
        cssVariable: "--h-list-item",
      },
      {
        label: "Item gap",
        value: "16px",
        cssVariable: "--gap-list-item",
      },
      {
        label: "Item padding vertical",
        value: "16px",
        cssVariable: "--pv-list-item",
      },
      {
        label: "Item padding horizontal",
        value: "16px",
        cssVariable: "--ph-list-item",
      },
      {
        label: "Item background color",
        value: "--c-neutral--50",
        cssVariable: "--c-list-item-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Item border radius",
        value: "4px",
        cssVariable: "--br-list-item",
      },
      {
        label: "Item border width",
        value: "1px",
        cssVariable: "--bw-list-item",
      },
      {
        label: "Item border color",
        value: "--c-neutral--100",
        cssVariable: "--bc-list-item",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Add button background color",
        value: "--c-primary",
        cssVariable: "--c--list-add--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Add button text color",
        value: "--c-on-primary",
        cssVariable: "--c--list-add--text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.TABLE,
    types: [ElementType.TABLE],
    properties: [
      {
        label: "Table header background color",
        value: "--c-white",
        cssVariable: "--c-table-header-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Child table header background color",
        value: "--c-neutral--200",
        cssVariable: "--c-child-table-header-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Table header text color",
        value: "--c-neutral--500",
        cssVariable: "--c-table-header-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Table text color",
        value: "--c-neutral--800",
        cssVariable: "--c-table-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Table background color",
        value: "--c-white",
        cssVariable: "--c-table-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Child table background color",
        value: "--c-neutral--100",
        cssVariable: "--c-child-table-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Table border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-table",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Cell gap",
        value: "10px",
        cssVariable: "--gap-table-cell",
      },
      {
        label: "Cell padding vertical",
        value: "8px",
        cssVariable: "--pv-table-cell",
      },
      {
        label: "Cell padding horizontal",
        value: "8px",
        cssVariable: "--ph-table-cell",
      },
      {
        label: "Add button background color",
        value: "--c-primary",
        cssVariable: "--c--table-add-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Add button text color",
        value: "--c-on-primary",
        cssVariable: "--c--table-add-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.COLUMNS,
    types: [ElementType.COLUMNS],
    properties: [
      {
        label: "Width",
        value: "100%",
        cssVariable: "--w-columns",
      },
      {
        label: "Height",
        value: "inherit",
        cssVariable: "--h-columns",
      },
      {
        label: "Padding vertical",
        value: "16px",
        cssVariable: "--pv-columns",
      },
      {
        label: "Padding horizontal",
        value: "16px",
        cssVariable: "--ph-columns",
      },
      {
        label: "Background color",
        value: "--c-white",
        cssVariable: "--c-columns-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Border radius",
        value: "4px",
        cssVariable: "--br-columns",
      },
      {
        label: "Border width",
        value: "1px",
        cssVariable: "--bw-columns",
      },
      {
        label: "Border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-columns",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Gap",
        value: "10px",
        cssVariable: "--gap-columns",
      },
      {
        label: "Min width column",
        value: "150px",
        cssVariable: "--min-w-column",
      },
      {
        label: "Min height column",
        value: "84px",
        cssVariable: "--min-h-column",
      },
      {
        label: "Column padding vertical",
        value: "16px",
        cssVariable: "--pv-column",
      },
      {
        label: "Column padding horizontal",
        value: "16px",
        cssVariable: "--ph-column",
      },
      {
        label: "Column background color",
        value: "--c-neutral--50",
        cssVariable: "--c-column-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Column border radius",
        value: "0",
        cssVariable: "--br-column",
      },
      {
        label: "Column border width",
        value: "1px",
        cssVariable: "--bw-column",
      },
      {
        label: "Column border color",
        value: "--c-neutral--100",
        cssVariable: "--bc-column",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.STEPPER,
    types: [ElementType.STEPPER],
    properties: [
      {
        label: "Padding vertical",
        value: "16px",
        cssVariable: "--pv-stepper",
      },
      {
        label: "Padding horizontal",
        value: "16px",
        cssVariable: "--ph-stepper",
      },
      {
        label: "Gap",
        value: "10px",
        cssVariable: "--gap-stepper",
      },
      {
        label: "Surface background color",
        value: "--c-neutral--50",
        cssVariable: "--c-stepper-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Surface border radius",
        value: "4px",
        cssVariable: "--br-stepper-surface",
      },
      {
        label: "Surface border width",
        value: "1px",
        cssVariable: "--bw-stepper-surface",
      },
      {
        label: "Surface border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-stepper-surface",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Circle color",
        value: "--c-neutral--300",
        cssVariable: "--c-stepper-circle",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Circle color active",
        value: "--c-primary",
        cssVariable: "--c-stepper-circle--active",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Line color",
        value: "--c-neutral--300",
        cssVariable: "--c-stepper-line",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Next button background color",
        value: "--c-primary",
        cssVariable: "--c--stepper-next--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Next button text color",
        value: "--c-on-primary",
        cssVariable: "--c--stepper-next--text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Prev button background color",
        value: "--c-neutral--300",
        cssVariable: "--c--stepper-prev--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Prev button text color",
        value: "--c-neutral--900",
        cssVariable: "--c--stepper-prev--text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.TABS,
    types: [ElementType.TABS],
    properties: [
      {
        label: "Gap",
        value: "10px",
        cssVariable: "--gap-tabs-surface",
      },
      {
        label: "Padding vertical",
        value: "16px",
        cssVariable: "--pv-tabs-surface",
      },
      {
        label: "Padding horizontal",
        value: "16px",
        cssVariable: "--ph-tabs-surface",
      },
      {
        label: "Surface background color",
        value: "--c-neutral--50",
        cssVariable: "--c-tabs-surface-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Surface border radius",
        value: "4px",
        cssVariable: "--br-tabs-surface",
      },
      {
        label: "Surface border width",
        value: "1px",
        cssVariable: "--bw-tabs-surface",
      },
      {
        label: "Surface border color",
        value: "--c-neutral--300",
        cssVariable: "--bc-tabs-surface",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Tab border active",
        value: "--c-primary",
        cssVariable: "--c-tab-border--active",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Tab text active",
        value: "--c-neutral--800",
        cssVariable: "--c-tab-text--active",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.SIDE_PANEL,
    types: [ElementType.SIDE_PANEL],
    properties: [
      {
        label: "Gap",
        value: "16px",
        cssVariable: "--gap-side-panel",
      },
      {
        label: "Side panel padding vertical",
        value: "16px",
        cssVariable: "--pv-side-panel",
      },
      {
        label: "Side panel padding horizontal",
        value: "16px",
        cssVariable: "--ph-side-panel",
      },
      {
        label: "Header background color",
        value: "--c-white",
        cssVariable: "--c--side-panel--header-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Background color",
        value: "--c-white",
        cssVariable: "--c--side-panel--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Overlay color",
        value: "--c-neutral--500",
        cssVariable: "--c--side-panel--overlay--background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
    ],
  },
  {
    label: CSSGroups.ICON,
    types: [ElementType.ICON],
    properties: [
      {
        label: "Color",
        value: "--c-neutral--500",
        cssVariable: "--c-icon-color",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Color hover",
        value: "--c-neutral--500",
        cssVariable: "--c-icon-color--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Font size",
        value: "24px",
        cssVariable: "--fs-icon",
      },
    ],
  },
  {
    label: CSSGroups.DROPDOWN,
    types: [ElementType.DROPDOWN],
    properties: [
      {
        label: "Button label color",
        value: "--c-neutral--500",
        cssVariable: "--c-dropdown-button-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button background color",
        value: "--c-transparent",
        cssVariable: "--c-dropdown-button-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button background color hover",
        value: "--c-transparent",
        cssVariable: "--c-dropdown-button-background--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Button width",
        value: "inherit",
        cssVariable: "--w-dropdown-button",
      },
      {
        label: "Button height",
        value: "30px",
        cssVariable: "--h-dropdown-button",
      },
      {
        label: "Button padding vertical",
        value: "0px",
        cssVariable: "--pv-dropdown-button",
      },
      {
        label: "Button padding horizontal",
        value: "0px",
        cssVariable: "--ph-dropdown-button",
      },
      {
        label: "Button border radius",
        value: "4px",
        cssVariable: "--br-dropdown-button",
      },
      {
        label: "Button border width",
        value: "1px",
        cssVariable: "--bw-dropdown-button",
      },
      {
        label: "Button font size",
        value: "16px",
        cssVariable: "--fs-dropdown-button",
      },
      {
        label: "Button icon font size",
        value: "24px",
        cssVariable: "--fs-dropdown-button-icon",
      },
      {
        label: "Dropdown background color",
        value: "--c-white",
        cssVariable: "--c-dropdown-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown border color",
        value: "--c-neutral--300",
        cssVariable: "--c-dropdown-border",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown border radius",
        value: "4px",
        cssVariable: "--br-dropdown",
      },
      {
        label: "Dropdown item text color",
        value: "--c-neutral--600",
        cssVariable: "--c-dropdown-item-text",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown item text color on hover",
        value: "--c-neutral--600",
        cssVariable: "--c-dropdown-item-text--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown item background color",
        value: "--c-transparent",
        cssVariable: "--c-dropdown-item-background",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown item background color on hover",
        value: "--c-neutral--200",
        cssVariable: "--c-dropdown-item-background--hover",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown item font size",
        value: "16px",
        cssVariable: "--fs-dropdown-item",
      },
      {
        label: "Dropdown item icon font size",
        value: "20px",
        cssVariable: "--fs-dropdown-item-icon",
      },
      {
        label: "Dropdown divider color",
        value: "--c-neutral--300",
        cssVariable: "--c-dropdown-divider",
        type: ElementConfigType.CSS_VARIABLE_SELECT,
        group: CSSGroups.COLORS,
      },
      {
        label: "Dropdown width",
        value: "auto",
        cssVariable: "--w-dropdown",
      },
      {
        label: "Dropdown height",
        value: "auto",
        cssVariable: "--h-dropdown",
      },
    ],
  },
];
