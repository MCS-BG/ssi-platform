Card: #<!-- issue number; moves the card through the SSI Delivery board -->

## What and why

## Evidence
- [ ] CI is green (tests and `build_manifest --check`)
- [ ] Test output or screenshots pasted below

## Reviewer checklist (human-in-the-loop gate)
- [ ] The change matches the card's acceptance criteria
- [ ] Tests cover the change, including the failure path
- [ ] Generated manifests were rebuilt from source, not hand-edited
- [ ] No secrets, tokens, or personal data in the diff
- [ ] Staging impact understood (si-staging deploys on merge)
- [ ] Rollback is the previous release tag (Rollback Prod workflow)

Merging deploys to staging. Prod needs **Promote to Prod**, run by the repo owner.
