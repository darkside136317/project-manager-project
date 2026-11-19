"""Build one archive package (AIP) as a ZIP.

The physical layout follows appendices I and II of TT 05/2025/TT-BNV: METS + EAD + PREMIS at package and
representation levels, and the original files under representations/rep1/data. METS 1.12 is validated before
delivery (aip_schemas/METS.xsd, xlink.xsd), each EAD against the schema of its fields.

Copied from document_manager (services/exchange/aip.py, see docs/NGUON_GOC.md) and adapted: the documents are streamed
from the object store into the ZIP (a project's photos and drawings do not fit in memory) and checked against the
SHA-256 kept when they were filed; every format is accepted (photos, spreadsheets, drawings: the format is written in
the metadata); the creating agent is this application.
"""

import hashlib
import mimetypes
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

METS = "http://www.loc.gov/METS/"
XLINK = "http://www.w3.org/1999/xlink"
CSIP = "https://DILCIS.eu/XML/METS/CSIPExtensionMETS"
PREMIS = "http://www.loc.gov/premis/v3"
SCHEMAS = Path(__file__).with_name("aip_schemas")
PROFILE = "http://www.ra.ee/METS/v01/IP.xml"
AGENT = "Project Manager"

FILE_FIELDS = (
    "arcFileCode", "title", "maintenance", "mode", "language", "startDate",
    "endDate", "keyword", "totalDoc", "numberOfPaper", "numberOfPage", "format",
    "inforSign", "confidenceLevel", "paperFileCode", "description", "riskRecovery",
    "riskRecoveryStatus",
)
DOCUMENT_FIELDS = (
    "arcFileCode", "mode", "language", "keyword", "numberOfPage", "format",
    "inforSign", "confidenceLevel", "description", "docCode", "docOrdinal",
    "typeName", "codeNumber", "codeNotation", "issuedDate", "organName",
    "subject", "autograph", "process",
)


class ChecksumMismatch(ValueError):
    """A document's content is not the one filed."""


def _tag(namespace, name):
    return f"{{{namespace}}}{name}"


def _xml(root):
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)


def _uuid():
    return str(uuid.uuid4()).upper()


def _ead_schema(fields):
    ns = "http://www.w3.org/2001/XMLSchema"
    schema = etree.Element(_tag(ns, "schema"), nsmap={"xs": ns},
                           elementFormDefault="qualified", attributeFormDefault="unqualified")
    group = etree.SubElement(schema, _tag(ns, "group"), name="elementsGroup")
    sequence = etree.SubElement(group, _tag(ns, "sequence"))
    for name in fields:
        etree.SubElement(sequence, _tag(ns, "element"), name=name, type="xs:string")
    container = etree.SubElement(schema, _tag(ns, "complexType"), name="elementContainer")
    choice = etree.SubElement(container, _tag(ns, "choice"))
    etree.SubElement(choice, _tag(ns, "group"), ref="elementsGroup")
    etree.SubElement(schema, _tag(ns, "element"), name="simpledc", type="elementContainer")
    return _xml(schema)


def _ead(fields, values):
    root = etree.Element("simpledc")
    for name in fields:
        etree.SubElement(root, name).text = str(values.get(name) or "")
    return _xml(root)


def _premis(objid, items):
    root = etree.Element(_tag(PREMIS, "premis"), nsmap={None: PREMIS}, version="3.0")
    for item in items:
        obj = etree.SubElement(root, _tag(PREMIS, "object"))
        ident = etree.SubElement(obj, _tag(PREMIS, "objectIdentifier"))
        etree.SubElement(ident, _tag(PREMIS, "objectIdentifierType")).text = "local"
        etree.SubElement(ident, _tag(PREMIS, "objectIdentifierValue")).text = item.get("name") or objid
        characteristics = etree.SubElement(obj, _tag(PREMIS, "objectCharacteristics"))
        fixity = etree.SubElement(characteristics, _tag(PREMIS, "fixity"))
        etree.SubElement(fixity, _tag(PREMIS, "messageDigestAlgorithm")).text = "SHA-256"
        etree.SubElement(fixity, _tag(PREMIS, "messageDigest")).text = item["sha256"]
        etree.SubElement(characteristics, _tag(PREMIS, "size")).text = str(item["size"])
    return _xml(root)


def _mets(objid, title, files, descriptive, preservation, *, kind, created):
    root = etree.Element(_tag(METS, "mets"), nsmap={None: METS, "xlink": XLINK, "csip": CSIP},
                         OBJID=objid, LABEL=title, TYPE="Mixed" if kind == "AIP_hoso" else "Collection",
                         PROFILE=PROFILE)
    header = etree.SubElement(root, _tag(METS, "metsHdr"), CREATEDATE=created, RECORDSTATUS="NEW")
    header.set(_tag(CSIP, "OAISPACKAGETYPE"), "AIP")
    agent = etree.SubElement(header, _tag(METS, "agent"), ROLE="CREATOR", TYPE="OTHER", OTHERTYPE="SOFTWARE")
    etree.SubElement(agent, _tag(METS, "name")).text = AGENT
    dmd = etree.SubElement(root, _tag(METS, "dmdSec"), ID="dmd-1", CREATED=created)
    ref = etree.SubElement(dmd, _tag(METS, "mdRef"), LOCTYPE="URL", MDTYPE="OTHER", OTHERMDTYPE="EAD")
    ref.set(_tag(XLINK, "href"), descriptive)
    amd = etree.SubElement(root, _tag(METS, "amdSec"), ID="amd-1")
    prov = etree.SubElement(amd, _tag(METS, "digiprovMD"), ID="premis-1", CREATED=created)
    ref = etree.SubElement(prov, _tag(METS, "mdRef"), LOCTYPE="URL", MDTYPE="PREMIS")
    ref.set(_tag(XLINK, "href"), preservation)
    section = etree.SubElement(root, _tag(METS, "fileSec"))
    group = etree.SubElement(section, _tag(METS, "fileGrp"), USE="Content")
    structure = etree.SubElement(root, _tag(METS, "structMap"), TYPE="physical")
    division = etree.SubElement(structure, _tag(METS, "div"), TYPE=kind, LABEL=title)
    for number, item in enumerate(files, 1):
        file_id = f"file-{number}"
        entry = etree.SubElement(group, _tag(METS, "file"), ID=file_id,
                                 MIMETYPE=item["mime"], SIZE=str(item["size"]),
                                 CHECKSUM=item["sha256"], CHECKSUMTYPE="SHA-256", CREATED=created)
        loc = etree.SubElement(entry, _tag(METS, "FLocat"), LOCTYPE="URL")
        loc.set(_tag(XLINK, "href"), item["name"])
        child = etree.SubElement(division, _tag(METS, "div"), TYPE="FILE", LABEL=item["name"])
        etree.SubElement(child, _tag(METS, "fptr"), FILEID=file_id)
    return _xml(root)


def _verify_mets(xml):
    parser = etree.XMLParser(no_network=True, resolve_entities=False)
    schema = etree.XMLSchema(etree.parse(str(SCHEMAS / "METS.xsd"), parser))
    schema.assertValid(etree.fromstring(xml, parser))


def _verify_ead(xml, schema):
    validator = etree.XMLSchema(etree.fromstring(schema))
    validator.assertValid(etree.fromstring(xml))


def build_package(destination, fonds_code, title, metadata, documents) -> dict:
    """Write an AIP_hoso ZIP at `destination` (a path that must not exist yet).

    `documents`: [{"suffix", "chunks" (a function giving the content's chunks), "sha256", "size", "mime",
    "metadata" (DOCUMENT_FIELDS)}], in order. Returns {"objid", "documents", "bytes", "sha256"}."""
    if not documents:
        raise ValueError("Hồ sơ không có tài liệu")
    created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    objid = f"urn:{fonds_code}:uuid:{_uuid()}"
    root_name = objid.replace(":", "_")
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)

    items = []
    for number, source in enumerate(documents, 1):
        suffix = (source.get("suffix") or "").lower()
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        name = f"data/File{number}{suffix}"
        items.append({**source, "name": name, "sha256": source["sha256"].upper(), "size": int(source["size"]),
                      "mime": source.get("mime") or mimetypes.guess_type(name)[0] or "application/octet-stream"})

    top_schema, doc_schema = _ead_schema(FILE_FIELDS), _ead_schema(DOCUMENT_FIELDS)
    top_ead = _ead(FILE_FIELDS, metadata)
    _verify_ead(top_ead, top_schema)
    rep_mets = _mets(objid + ":rep1", title, items, "metadata/descriptive/EAD_doc_File1.xml",
                     "metadata/preservation/PREMIS_rep1.xml", kind="AIP_hoso", created=created)
    _verify_mets(rep_mets)
    rep_path = "representations/rep1/METS.xml"
    rep_info = {"name": rep_path, "size": len(rep_mets), "sha256": hashlib.sha256(rep_mets).hexdigest().upper(),
                "mime": "application/xml"}
    top_mets = _mets(objid, title, [rep_info], "metadata/descriptive/EAD.xml", "metadata/preservation/PREMIS.xml",
                     kind="AIP_hoso", created=created)
    _verify_mets(top_mets)

    try:
        with zipfile.ZipFile(output, "x", allowZip64=True) as archive:
            def write(name, data):
                archive.writestr(f"{root_name}/{name}", data, compress_type=zipfile.ZIP_DEFLATED)

            write("METS.xml", top_mets)
            write("metadata/descriptive/EAD.xml", top_ead)
            write("metadata/preservation/PREMIS.xml", _premis(objid, [rep_info]))
            write("schemas/METS.xsd", (SCHEMAS / "METS.xsd").read_bytes())
            write("schemas/xlink.xsd", (SCHEMAS / "xlink.xsd").read_bytes())
            write("schemas/EAD.xsd", top_schema)
            write("schemas/EAD_doc.xsd", doc_schema)
            write(rep_path, rep_mets)
            write("representations/rep1/metadata/preservation/PREMIS_rep1.xml", _premis(objid, items))
            for number, item in enumerate(items, 1):
                document_ead = _ead(DOCUMENT_FIELDS, item.get("metadata") or {})
                _verify_ead(document_ead, doc_schema)
                write(f"representations/rep1/metadata/descriptive/EAD_doc_File{number}.xml", document_ead)
                info = zipfile.ZipInfo(f"{root_name}/representations/rep1/{item['name']}")
                info.compress_type = zipfile.ZIP_STORED
                digest = hashlib.sha256()
                with archive.open(info, "w", force_zip64=True) as target:
                    for chunk in item["chunks"]():
                        digest.update(chunk)
                        target.write(chunk)
                if digest.hexdigest().upper() != item["sha256"]:
                    raise ChecksumMismatch(f"Tài liệu số {number} không còn như lúc nộp lưu")
        digest = hashlib.sha256()
        with open(output, "rb") as built:
            for block in iter(lambda: built.read(1024 * 1024), b""):
                digest.update(block)
        return {"objid": objid, "documents": len(items), "bytes": output.stat().st_size,
                "sha256": digest.hexdigest()}
    except Exception:
        output.unlink(missing_ok=True)
        raise
