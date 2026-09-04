# Chart-engine licensing and SBOM gate

**Дата:** 2026-08-25  
**Status:** **BLOCKED for public commercial release** until owner/legal sign-off is recorded.

## Current dependency inventory

| Component | Pinned/current version | Role | Public license evidence | Gate status |
|---|---:|---|---|---|
| Kerykeion | 5.12.9 | Canonical calculation dependency and server-side chart drawer | AGPL-3.0 in repository/package metadata [1] [2] | **Blocked** pending commercial distribution decision |
| Swiss Ephemeris / pyswisseph | pyswisseph 2.10.3.2 | Ephemeris calculation underneath the existing production path | Swiss Ephemeris official page documents AGPL or Professional License choice [3] | **Blocked** pending license choice and proof |
| resvg_py | 0.5.0 | Transient SVG-to-PNG rasterizer | Python binding documents MIT; upstream resvg documents MIT/Apache-2.0 [4] [5] [6] | Technically acceptable; Docker/runtime verification open |
| Pillow | 12.3.0 | WebP encoding and existing image cards | Existing project dependency; verify in final SBOM | Open routine inventory gate |
| WeasyPrint | `>=62.0` | HTML-to-PDF output | Existing project dependency; verify transitive licenses in final SBOM | Open routine inventory gate |

## Required sign-off package

Before a commercial/public deployment, the owner must attach a dated legal decision that answers whether the service will comply with AGPL obligations for the combined Kerykeion/Swiss Ephemeris path or obtain the applicable Swiss Ephemeris Professional License. The decision must identify the distributor/entity, deployment model, source-availability obligations if applicable, and the exact package versions reviewed.

The release package must include a generated SBOM from the production lockfile/image, license notices for direct and transitive dependencies, a record that `resvg_py` is present and importable in the target image, and a Docker build/runtime smoke. The current sandbox cannot run Docker, so that evidence is not yet available.

## Prohibited claims

The repository must not claim that AGPL/Swiss licensing is solved merely because the technical adapter works, because Kerykeion is already present in `astro.py`, or because the API is authenticated. A technically correct private render is not a legal approval. Until sign-off exists, launch governance remains **no-go for public commercial release**.

## References

[1]: https://github.com/g-battaglia/kerykeion "Kerykeion repository and license metadata"  
[2]: https://pypi.org/project/kerykeion/ "Kerykeion PyPI metadata"  
[3]: https://www.astro.com/swisseph/ "Swiss Ephemeris official licensing page"  
[4]: https://pypi.org/project/resvg_py/ "resvg_py PyPI metadata"  
[5]: https://github.com/baseplate-admin/resvg-py "resvg-py binding repository"  
[6]: https://resvg-py.readthedocs.io/en/latest/license.html "resvg-py license documentation"  
[7]: https://github.com/linebender/resvg "upstream resvg repository"
