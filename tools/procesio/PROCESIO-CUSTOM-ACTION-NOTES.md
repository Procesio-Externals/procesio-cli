# PROCESIO C# Custom Actions — packaging, whitelist, and the file channel

What the platform documents about the **C# Custom Action** (`.nupkg` upload), and how
that compares with the scripting actions. Everything below is **vendor-documented**,
read from `docs.procesio.com/llms-full.txt`, and is labelled as such: none of it has
been executed against a live instance from this framework. Read
[`PROCESIO-NODE-MODULE-WHITELIST.md`](PROCESIO-NODE-MODULE-WHITELIST.md) for the
sandbox facts that **were** probed live.

## The build contract

- **C# only**, class library, implementing `IAction` from `Ringhel.Procesio.Action.Core`
  with `ClassDecorator` / `FEDecorator` / `BEDecorator` / `Validator` attributes.
- **Runtime is documented contradictorily**: the rules page and the guide prose say
  .NET Core 3.1, while both `.csproj` samples say `<TargetFramework>net6.0</TargetFramework>`
  and a third page says ".Net 6". Upload runs server-side validations, so a wrong target
  fails late, at upload, not at build. **Target `net6.0` and keep 3.1 as the fallback.**
- The core package comes from a **GitHub Packages feed** and needs a GitHub PAT with
  `read:packages`. It is not on nuget.org.
- The `.csproj` must set `CopyLocalLockFileAssemblies`, `GeneratePackageOnBuild` and an
  `IncludeDepsInPackage` target, because **dependencies ship inside the `.nupkg`**.

## Lifecycle — plan for it, it is unusually rigid

- **A Custom Action cannot be updated in place.** The only route is a new package version
  and a fresh create.
- **It cannot be deleted once used in at least one process.** Deletion is guaranteed only
  while the action has never been placed on a canvas. **Anything that promises to clean up
  after itself must either never drag the action onto a process, or exercise it through the
  action's own test area** (`IsTestable = true` opens one), or the cleanup fails by design.

## The dependency whitelist — two lists, and the second is the sharp one

"Other libraries that are not offered by Microsoft need to be whitelisted with us." The
docs publish both lists as a JSON configuration block.

**Packages:** `Ringhel.Procesio.Action.Core`, `Newtonsoft.Json`, `JetBrains.Annotations`,
`SimMetrics.Net`, `CsvHelper`, `DocumentFormat`, `DocumentFormat.OpenXml`,
`DocumentFormat.OpenXml.Packaging`, `DocumentFormat.OpenXml.Spreadsheet`, `Ical.Net`.

**Namespaces:** the packages above plus `System.Runtime`, `System.Linq`,
`System.Threading.Tasks`, `System.Collections`, `System.Private.CoreLib`,
`System.Private.Uri`, `corlib`, `System.Text.RegularExpression`,
`System.Diagnostics.Debug`, `System.ComponentModel`, `System.Data`, `System.Console`,
and five `System.Net.*` entries.

Four things fall out, and they decide designs:

1. **The package list allows OpenXml; the namespace list only names `.Packaging` and
   `.Spreadsheet`.** `DocumentFormat.OpenXml.Wordprocessing` (a DOCX body) and
   `DocumentFormat.OpenXml.Presentation` (a PPTX) are **absent**. So the documented
   capability is **XLSX-shaped**, and the common assumption that one library buys three
   formats does not survive the namespace list. Untested; treat DOCX and PPTX in C# as
   unproven until someone runs it.
2. **`System.IO` is absent** while the core assemblies are present. The file example in
   the same docs uses a `Stream`. Read that as **streams yes, file system unstated** —
   and do not design against a temp path without measuring first.
3. **Also absent**: `System.Net.Http`, `System.Security.Cryptography`, `System.Text.Json`,
   `System.IO.Compression`. No PDF library of any kind appears, so **PDF inside a Custom
   Action is a vendor request**, while PDF text extraction is available with no gate at all
   through the native action and the Python action.
4. **The published list contains two misspellings**, `WhitelistNamesapaces` and
   `System.Text.RegularExpression` in the singular. If namespaces are matched literally,
   `System.Text.RegularExpressions` is not whitelisted. A typo inside an allowlist is
   load-bearing; verify before relying on regex.

The whitelist is published **as a configuration block**, which is a deployment-owned
artefact. Whether a self-hosted operator can edit it, and therefore whether the dependency
constraint is topology-dependent, **is not documented**. Ask before promising a customer a
library that is not on the list.

## How a file reaches a Custom Action — a stream, never a path

```csharp
IEnumerable<FileModel> FileList { get; set; }   // or a single FileModel

foreach (var file in FileList)
{
    _ = file.Name;              // string
    _ = file.File;              // Stream — the content
}
```

`FileModel` has exactly two properties, `Name` and `File`. The front end binds it with
`[FEDecorator(Type = FeComponentType.File)]` against a file-typed process variable.
**Nothing in the documentation states that a Custom Action has a file system**, in either
direction, and nothing states whether anything written during one invocation survives into
the next. Both are open questions, and the second one is the expensive one: a per-run
filesystem and no filesystem look identical in the docs and behave very differently across
an async split.

## The scripting actions, for comparison

Four exist, and they are not one sandbox with four languages.

| Action | Libraries | File position |
|---|---|---|
| **Javascript** | none ("no access to specific libraries") | — |
| **Node** | a fixed list of **24**, no additions | docs state plainly it "does not support working with files" |
| **Python** | 9 preinstalled, including **pdfplumber**, **PyPDF2**, **pandas**, **spacy**, **pillow** | "Files cannot be added in Python script", then the base64 bridge below |
| **Ruby** | 9 gems, none document-related | — |

**The platform's documented file channel for a script is base64 through process
variables**, not a file system: `File to BASE64` turns a File variable into a string, the
script works on the string, and `Base64 to File` turns the result back into a File. Use
that bridge rather than looking for a path.

## Before building a Custom Action, check the catalogue

A large amount of file work needs no custom code, no upload and no whitelisting request:

- **PDF**: Extract Text (returns concatenated text **plus** per-word JSON with position and
  font), Extract Embedded Files, Area Mapper, Merge Files, Select/Remove pages,
  Acroform Insert Image.
- **Excel**: Create Workbook, Split Workbook, XLS To XLSX, Insert/Rename/Delete Sheet,
  Get Sheet Names, Read Range, Read Range from CSV, Copy Paste, Apply Formula,
  Get Named Range, Get Last Used Row.
- **Documents**: Generate Document (from a Document Designer template), HTML to PDF,
  DOCX to PDF, DOCX to HTML, Word Mail Merge, Export to CSV/XLSX, Write (list) to file,
  Read file, File to Base64, plus an Archive sub-folder for compress and decompress.

**Rule of thumb: catalogue action first, then Python action, then Node, then a Custom
Action.** The order tracks cost — the first three need no upload, no versioning ritual, no
GitHub PAT and no vendor whitelisting request, and only the Custom Action carries a
lifecycle you cannot undo.

## Documented size limits — and which ones do not apply

| Limit | Applies to |
|---|---|
| 100 MB | FTP/sFTP **Download File** |
| 1 GB | FTP/sFTP **Upload File** |
| 500 MB (default `maxfilesize`) | form **File Upload** element |

**None of these binds a Custom Action.** No size limit, timeout, memory limit or
concurrency statement is documented for Custom Actions at all. Measure before quoting a
figure to anyone.
