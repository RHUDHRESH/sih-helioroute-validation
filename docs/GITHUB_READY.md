# Repository preparation

This folder is a standalone Git repository prepared for publication. The source, documentation, baseline replay, expanded study CSV/JSON, compressed raw dispatches, plots and evidence hashes are included. Local virtual environments, caches and duplicate Windows baseline runs are excluded.

The validation workflow runs the Python baseline and an independently audited reduced study. The [initial release passed hosted CI](https://github.com/RHUDHRESH/sih-helioroute-validation/actions/runs/37095304743). The workflow uses Python entrypoints directly so archive extraction does not depend on Unix executable file permissions.

Remote: `RHUDHRESH/sih-helioroute-validation`, created with private visibility. Research documentation, computed scientific figures and the codebase are included. App screenshots are excluded. To push subsequent commits:

```sh
git push -u origin main
```

The local commits use the configured Git identity. Publication archives are generated from Git-tracked files and exclude environments, credentials, local tool metadata and app screenshots. No third-party dataset or real electrical measurement is included. See STUDY_REPORT.md for evidence boundaries and reproduction commands.
