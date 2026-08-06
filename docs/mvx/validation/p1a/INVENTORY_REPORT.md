# MVX P1a — corpus census checkpoint

Status: **descriptive snapshot frozen; G1 not yet passed**.

## Objaverse live snapshot

Two read-only inventories of the private Morphoia Objaverse folder returned the
same canonical bytes and SHA-256. This supports freezing the current folder
state as candidate snapshot `MORPHOIA-OBJAVERSE-2026-08-06-A`.

| Measure | Value |
|---|---:|
| Drive items | 964 |
| GLB files | 962 |
| Unique Objaverse UIDs | 961 |
| Labels represented | 197 |
| Total bytes | 5,857,446,272 |
| Duplicate UID groups | 1 |
| Explicit non-GLB test files | 2 |
| Raw private snapshot SHA-256 | `232105003af4081d12e6fd30899003eed8cc2d71dc4ffafad47bdd3b834cb08f` |

The raw snapshot, Drive IDs, file paths and UID list are private inputs. Only
aggregate counts and the commitment are committed to the repository.

## Stale manifest reconciliation

The local manifest contains 26,996 **file rows**, 420,012,777,690 bytes and no
SHA-256 values. It must not be interpreted as 26,996 independent 3D objects.
Archives, multipart fragments and sidecars require object-level reconstruction
before lineage assignment.

| Manifest dataset | File rows |
|---|---:|
| MedShapeNet | 24,567 |
| Google Scanned Objects | 1,035 |
| Objaverse | 674 |
| Thingi10K | 243 |
| Smithsonian 3D | 155 |
| MaizeField3D | 98 |
| Pheno4D | 86 |
| PLANesT-3D | 80 |
| ModelNet40 | 40 |
| BodyParts3D | 12 |
| MedShapeNetCore | 6 |

The stale manifest lists 672 Objaverse GLBs and two test text files. The stable
live snapshot has 962 GLBs, so the live folder is authoritative for P1a.

## Known exclusions and pending evidence

- The two explicit test text files are not object candidates.
- The two GLBs sharing one UID form one lineage candidate until hash/geometry
  adjudication; they cannot count twice.
- Per-UID author, source and licence metadata are not present locally and remain
  `PENDING`.
- No external UID lookup was performed, because disclosing membership derived
  from a private Drive corpus to a public service requires separate authority.
- P2a must still assign format status, V/O/N/U and complexity quantile without
  looking at any MVX reconstruction outcome.

## Gate effect

This checkpoint authorises continued local census and P2a planning only. It
does **not** satisfy G1: no 1,000-lineage cohort, reserve, blind assignment or
experimental MVX run has been created.
