# Paired Chrome inputs for hosted browser controls

The [input plan](../tools/dependency-review/browser-inputs.json) binds the full
Linux x64 Chrome archives selected by the two reviewed Puppeteer publications.
The browser revision declarations are verified against their retained npm
publication members. Chrome for Testing version metadata is pinned to an
immutable commit of the official GoogleChromeLabs repository; the selected
public Google Cloud Storage object generations are also recorded.

| SDK profile | Puppeteer | Chrome for Testing | Archive bytes | Regular files | Expanded bytes |
| --- | --- | --- | ---: | ---: | ---: |
| Baseline | 25.12.0 | 154.0.8037.57 | 196,223,440 | 301 | 411,698,200 |
| Candidate | 25.17.0 | 157.0.8103.50 | 203,527,334 | 301 | 427,261,066 |

Both archives were acquired once as complete streams with explicit byte caps.
The observed official generation, length and MD5 values match. Each complete
archive also has a separately verified SHA-256 pin. The retained input has one
protected object per archive digest; there is no local extracted browser tree.

The read-only inspector verifies the raw pin before interpreting ZIP metadata.
It bounds raw bytes, central-directory bytes, member count, each expanded member
and aggregate expansion. It refuses nonregular entries, path traversal,
protected names, case aliases, file/ancestor conflicts, encrypted members,
unsupported compression and multi-disk/trailing/commented archive envelopes.
Every regular member is read completely with its ZIP CRC and SHA-256 checked.
The Chrome executable has the expected 64-bit little-endian x86-64 ELF shape.
These checks are bounded input inspection, not general ZIP conformance or proof
of executable behavior.

The original `ABOUT` and `WidevineCdm/LICENSE` members are retained within each
unchanged archive and represented in its file inventory. Content pins and the
ELF shape do not establish publisher signatures, a reproducible Chromium build,
complete legal review, installed system dependencies or working browser APIs.
The binaries and extracted trees are not repository or application payloads.

Sixteen memory-only archive controls cover positive and refusal behavior. No
on-disk link, FIFO, socket or browser fixture is created by those controls. The
complete real-archive inspection runs with operating-system filesystem writes
and network access denied. Neither archive is extracted or executed locally.

The current CI continues its existing build, parser/mapper and actual installed
Node consumer controls. The new archive controls run in the data-test lane.
Real Chrome/CDP/BiDi execution, system-library compatibility, browser rendering,
and application behavior are **NOT_RUN** for this input checkpoint. Browser IPC
and runtime fixtures belong in the separately bounded hosted lane.

The tracked application source has no deployment records. Its nominal build
and any future build with an explicitly synthetic deployment fixture require
separate evidence; a fixture is not an operator deployment or chain observation.
The [Node consumer boundary](NODE_CONSUMER_CONTROLS.md), raw candidate status,
separate derived mapper/parser fixes, platform and owner gates remain in force.
The application migration is unadopted and production remains **NO_GO**.
