"""Romanian catalogue for this distribution.

Generated from the publication plan. `framework-map check` lists anything
a new component adds that is not translated here yet.
"""
from __future__ import annotations

# category labels
CATS = {
    "Data & databases": "Date & baze de date",
    "Framework core": "Nucleul framework-ului",
    "Other": "Altele",
    "PROCESIO & automation": "PROCESIO & automatizare",
    "Web automation": "Automatizare web",
}

TOOL_DESC = {
    "connector-builder": "AI Connector Builder (connector-builder.procesio.app): transformă documentația unui API într-un connector .nupkg de Custom Action PROCESIO compilat, printr-un pipeline LLM în 8 etape (gather -> clarify -> plan -> generate -> validate -> compile -> fix -> deliver). Conduce tot ciclul de build, citește/scrie fișierele generate, descarcă artefactul .nupkg (de urcat în PROCESIO pentru testare live), inspectează logurile/telemetria și editează baza de cunoștințe a builder-ului (prompturi, module de spec, exemple, reguli de validare). Două moduri de auth, ambele -> token Bearer: o cheie API acb_, sau username/parolă via /auth/login.",
    "framework-map": "Regenerează harta framework-ului, interactivă și bilingvă (EN implicit / RO) - un singur fișier HTML autonom care vizualizează fiecare tool, agent, skill și acțiune din registrul viu (până la nivel de argument), plus bucla de orchestrare, diagrama cine-declanșează-ce, programările, memoria de context/stare/cunoștințe și exemple de utilizare. Făcut pentru a prezenta framework-ul Agents-and-Tools unei echipe.",
    "mysql": "Interogări MySQL/MariaDB read-only peste pymysql, cu profile de conexiune numite. Implicit doar SELECT (--write pentru a suprascrie); întoarce rânduri ca JSON; introspecție de schemă/tabele. MySQL nu are un intent de read-only, deci write-guard-ul e mecanismul de forțare.",
    "procesio": "Platforma de automatizare low-code PROCESIO (procesio.app/.com). Acoperire 1:1 completă a Web API-ului: fiecare endpoint e o acțiune (nume <metodă>-<cale>) plus scurtături ergonomice, un `request` generic și un `export` (transport .procesio). Auth duală (cheie API per-workspace, sau sesiune cookie username/parolă) cu un depozit de profile multi-credential; --profile alege contul/cheia, --workspace-id setează workspace-ul activ.",
    "sqlserver": "Interogări SQL Server read-only peste pyodbc, cu profile de conexiune numite. Implicit doar SELECT (--write pentru a suprascrie); întoarce rânduri ca JSON; introspecție de schemă/tabele.",
    "web": "Conduce aplicații web care NU au API prin Playwright, refolosind sesiuni de login SALVATE ca să ne autentificăm o dată și să reutilizăm. Sesiunile sunt Playwright storageState (cookie-uri + localStorage) per site numit, stocate gitignored sub tools/web/sessions/<name>.json - țin auth live și sunt SENSIBILE (niciodată comise, niciodată afișate). Alte tool-uri și agentul de outreach îl apelează ori de câte ori trebuie să se conecteze la un site sau să facă research web mai adânc. Pe bază de acțiuni. Fără API HTTP; o abstracție BrowserDriver împachetează Playwright (importat lazy) ca tool-ul să se încarce chiar și înainte ca browserele să fie instalate. SESIUNI DEȚINUTE DE BROKER: run/get-text/screenshot pe o sesiune deținută de un broker de serializare (whatsapp/ryver/fgo/mirro) rulează ÎN acel broker, serializate cu comenzile tool-ului proprietar. --direct trece peste (backup).",
    "xlsx": "Citește workbook-uri Excel locale (.xlsx/.xlsm) - listează foi, citește o foaie ca JSON, sau aruncă tot fișierul în text. Fără credentiale.",
}

AGENT_DESC = {
    "connector-builder": "Agent de orchestrare pentru construirea de connectoare PROCESIO. Conduce tool-ul `connector-builder` (clientul REST al AI Connector Builder de la connector-builder.procesio.app) și tool-ul `procesio` ca să ruleze bucla completă: generează un connector de Custom Action din documentația API → descarcă .nupkg-ul compilat → îl urcă în PROCESIO → îl testează live → întoarce eșecurile ca să îmbunătățească connectorul (și, pentru probleme sistemice, baza de cunoștințe a builder-ului). E partea executabilă a playbook-ului build→test→improve din acest folder și puntea către playbook-ul de build-and-test al agentului procesio. Mecanica tool-ului stă în tools/connector-builder/; metodologia stă aici.",
    "procesio": "Agent de build-and-test PROCESIO. Știe cum să creeze use case-uri, să editeze resurse și să îmbunătățească implementări pe platforma PROCESIO și impune disciplina de build-and-test: servește playbook-ul operațional + best practices, emite checklist-ul riguros de self-test, rulează o poartă de verify automatizabilă pe un proces live (validare, paritate designer-vs-runtime, rulare + citire status instanță) și auditează static un proces pentru mirosuri de ineficiență / UX / robustețe. Metodologia stă în acest folder; mecanica tool-ului stă în tools/procesio/.",
}

SKILL_DESC = {
    "agent-skill-engineer": "Proiectează, îmbunătățește și auditează pachete Agent Skill reutilizabile și sistemele de rutare și evaluare SKILL.md. Folosește-l când livrabilul principal este un Agent Skill: transformarea unui workflow repetat într-un skill, redactarea sau revizuirea unui SKILL.md ori a unui skill de domeniu, schimbarea descrierii sau limitelor de declanșare, separarea conținutului în referințe, scripturi sau assets progresive, construirea de baseline-uri și evaluări A/A sau A/B cu rubrică fixă ori auditarea unui pachet de skill. Nu pentru implementare obișnuită de repository, operații pe workspace, design generic de CLI, creare de imagini sau conținut one-off.",
    "procesio-cli": "Operează și depanează resurse PROCESIO prin CLI-ul sau MCP-ul acestui repository. Folosește-l când inspectezi, creezi, editezi, rulezi, validezi, auditezi, exporți, imporți, programezi, declanșezi, testezi sau verifici un proces, formular, document, webhook, credential, model de date, custom action, workspace sau instanță de execuție PROCESIO.",
    "procesio-cli-maintainer": "Schimbă sau revizuiește codul sursă și integrarea repository-ului procesio-cli. Folosește-l pentru acțiuni CLI, manifest, implementare, registru, server MCP, runtime de agent, router generat, sincronizare CLAUDE.md, porți CI, teste, gestionarea credentialelor, contracte JSON, reversibilitate și integrarea unui Agent Skill deja proiectat. Nu pentru operarea unui workspace sau când livrabilul principal este pachetul Agent Skill, conținutul SKILL.md, limitele de rutare ori evaluarea comportamentală a skill-ului.",
    "procesio-platform-advisor": "Evaluează dacă PROCESIO poate susține un workflow și ce arhitectură se potrivește. Folosește-l pentru capabilități de produs, fezabilitate, evaluarea use case-urilor, limite de integrare, prețuri PROCESIO, calcul de cost, câte EE-uri sunt necesare, dimensionarea capacității, comparații cu Zapier, Make, MuleSoft sau Workato, on-prem versus cloud, dovezi de conformitate, strategie RPA și prioritizarea proceselor de business înainte de implementare.",
    "sql-server-optimizer": "Analizează și optimizează T-SQL pentru SQL Server, inclusiv SQL rulat de PROCESIO. Folosește-l când revizuiești o interogare, procedură, funcție, plan de execuție, strategie de indexare, sargabilitate, parameter sniffing, conversii implicite, logical reads, blocking, performanța interogărilor de raportare, semantica rezultatelor, siguranța izolării sau parametrii inline/nativi PROCESIO; nu pentru PostgreSQL, MySQL sau mentenanța repository-ului.",
}

TRIG = {
    "approve / revise the plan / regenerate files / download the connector artifact": "aprobă / revizuiește planul / regenerează fișiere / descarcă artefactul connectorului",
    "audit a procesio process for best practices": "auditează un proces procesio pentru best practices",
    "build a PROCESIO custom action / connector from API docs": "construiește un custom action / connector PROCESIO din documentația API",
    "build a PROCESIO custom action / connector from API docs and test it": "construiește o custom action / un connector PROCESIO din documentația API și testează-l",
    "build a procesio use case": "construiește un use case procesio",
    "build the bilingual framework map (EN/RO)": "construiește harta bilingvă a framework-ului (EN/RO)",
    "create / run / drive an AI Connector Builder build": "creează / rulează / conduce un build AI Connector Builder",
    "delete a process / form / document / webhook / credential": "șterge un proces / formular / document / webhook / credential",
    "download a flow-instance file (Generate-Document output)": "descarcă un fișier de instanță de flux (output Generate-Document)",
    "drive the AI Connector Builder end to end (gather → plan → generate → compile)": "conduce AI Connector Builder de la cap la coadă (colectare → plan → generare → compilare)",
    "drive/scrape a website that has no API, using a saved login session; deeper web research": "conduce/scrapează un site fără API, cu o sesiune de login salvată; research web mai adânc",
    "duplicate a process / copy a process / clone a process": "duplică un proces / copiază un proces / clonează un proces",
    "edit the connector builder's prompts / spec modules / examples (improve generation)": "editează prompturile / modulele de spec / exemplele connector builder-ului (îmbunătățește generarea)",
    "export procesio": "export procesio",
    "generate a .nupkg connector for PROCESIO from documentation": "generează un connector .nupkg pentru PROCESIO din documentație",
    "how do I run the connector build → test → improve loop": "cum rulez bucla build → test → îmbunătățire a connectorului",
    "how should I build / test in procesio": "cum ar trebui să construiesc / testez în procesio",
    "import procesio / import a .procesio bundle": "import procesio / importă un bundle .procesio",
    "improve a procesio implementation": "îmbunătățește o implementare procesio",
    "launch procesio process": "lansează un proces procesio",
    "layout / re-lay-out a process canvas; read or inspect a flow graph": "aranjează / re-aranjează canvasul unui proces; citește sau inspectează un graf de flux",
    "list / add / set the default procesio environment (<Client>-<ENV>); bind a credential to an environment": "listează / adaugă / setează mediul procesio implicit (<Client>-<ENV>); leagă o credențială de un mediu",
    "list MySQL tables or columns": "listează tabele sau coloane MySQL",
    "list SQL Server tables or columns": "listează tabele sau coloane SQL Server",
    "list forms / list documents; get or toggle a process; AI Decisional": "listează formulare / documente; ia sau comută un proces; AI Decisional",
    "list procesio processes": "listează procesele procesio",
    "procesio": "procesio",
    "procesio api": "procesio api",
    "procesio endpoint": "procesio endpoint",
    "procesio export": "procesio export",
    "procesio instance": "procesio instance",
    "procesio workspace": "procesio workspace",
    "query a MySQL / MariaDB database": "interoghează o bază de date MySQL / MariaDB",
    "query a SQL Server / MSSQL database": "interoghează o bază de date SQL Server / MSSQL",
    "read a table from MySQL": "citește un tabel din MySQL",
    "read a table from SQL Server": "citește un tabel din SQL Server",
    "refresh the agents and tools diagram / presentation page": "împrospătează diagrama de agenți și tool-uri / pagina de prezentare",
    "regenerate / rebuild the framework map or the agents-and-tools visualization": "regenerează / reconstruiește harta framework-ului sau vizualizarea agents-and-tools",
    "run a MySQL query": "rulează o interogare MySQL",
    "run a SQL Server query": "rulează o interogare SQL Server",
    "run a procesio process": "rulează un proces procesio",
    "run procesio against QA / DEV / staging / a client installation": "rulează procesio pe QA / DEV / staging / o instalare de client",
    "switch procesio environment / work on PROCESIO Internal-QA / Internal-DEV / a client env": "schimbă mediul procesio / lucrează pe PROCESIO Internal-QA / Internal-DEV / un mediu de client",
    "test / verify a procesio process or resource": "testează / verifică un proces sau o resursă procesio",
    "test a credential connection / test a custom action": "testează o conexiune de credential / testează un custom action",
    "trigger procesio flow": "declanșează un flux procesio",
    "update the framework HTML with the new tools / agents / mechanics": "actualizează HTML-ul framework-ului cu tool-urile / agenții / mecanicile noi",
    "upload / install / delete / list a custom action (.nupkg connector)": "urcă / instalează / șterge / listează un custom action (connector .nupkg)",
    "upload a generated connector to PROCESIO and improve it from the feedback": "urcă un connector generat în PROCESIO și îmbunătățește-l din feedback",
    "validate a process (correctness oracle)": "validează un proces (oracol de corectitudine)",
    "what's the next step for this connector build": "care e următorul pas pentru acest build de connector",
    "which tools or agents changed / still need an RO translation": "ce tool-uri sau agenți s-au schimbat / mai au nevoie de traducere RO",
}
