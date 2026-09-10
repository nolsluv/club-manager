# Git Workflow — Club Manager

We use **GitHub Flow**: a lightweight branch-per-feature workflow. `main` should always be in a working state.

## The Rules

1. **Never push directly to `main`.** All work happens on a branch and merges in through a Pull Request (PR).
2. **Always branch from an up-to-date `main`.**
3. **One branch = one piece of work.** Keep branches small and focused so PRs are easy to review.
4. **Every PR needs at least one review** before merging, even a quick one.
5. **Delete branches after merging.** Keeps the branch list clean.

## Step by Step

### 1. Start from an updated main
```
git checkout main
git pull origin main
```

### 2. Create a branch
```
git checkout -b feature/short-description
```
**Naming convention:**
- `feature/...` — new functionality (e.g. `feature/member-signup`)
- `fix/...` — bug fixes (e.g. `fix/rsvp-count-error`)

Name describes the *work*, not the person.

### 3. Work and commit
Commit as you go, not just once at the end.
```
git add .
git commit -m "Add Member model with admin registration"
```

### 4. Push the branch
```
git push -u origin feature/short-description
```
(Only need `-u` the first time; after that just `git push`.)

### 5. Open a Pull Request
On GitHub, click **Compare & pull request**. In the description, cover:
- **What** changed (1–2 sentences)
- **Why** (what it unblocks or fixes)
- **How to test** it (steps a reviewer can actually run)
- **Notes** on anything intentionally left out

### 6. Get it reviewed
Tag a teammate. They should at least skim the diff before approving — catches bugs, accidental secrets, or scope creep early.

### 7. Merge and clean up
Once approved, merge on GitHub. Then locally:
```
git checkout main
git pull origin main
git branch -d feature/short-description
```

## Team Ownership

| Area | Owner |
|---|---|
| Members app | _TBD_ |
| Events app | _TBD_ |
| Finances app | _TBD_ |
| Core / shared setup / deployment | _TBD_ |

If your change touches another area (e.g. Events referencing the Member model), loop in that area's owner before merging.

## Why we do it this way

- Keeps `main` always deployable — nobody is blocked by someone else's half-finished work.
- PRs give a checkpoint to catch mistakes before they're permanent.
- Small, focused branches mean fewer merge conflicts and easier reviews.
