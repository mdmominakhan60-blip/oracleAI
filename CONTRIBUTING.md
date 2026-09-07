# Branching Policy — oracleAI

> Зафиксировано в BUS-484 по запросу владельца (BUS-482): master — единственная
> основная ветка; ветвление — только под задачу и только на время задачи.

## Основная ветка

- **master** — единственная основная ветка репозитория. Все релизные состояния
  берутся из master. Вторых long-lived веток (develop, release/*) нет.
- master синхронен между GitHub (origin) и GitLab (gitlab, резервный ремоут
  по решению владельца, BUS-475): `local master = origin/master = gitlab/master`.
- **Force-push в master запрещён.** Обновление gitlab/master — только fast-forward.

## Feature-ветки

- Формат имени: `feature/<issue>` или `fix/<issue>` (короткое пояснение можно
  добавить через дефис: `fix/bus468-pin-image-tag`).
- Ветка создаётся на задачу (issue), короткоживущая.
- После вливания в master (PR смержен или merge-коммит запушен) ветка
  **удаётся сразу** на всех уровнях: локально, origin (GitHub) и gitlab
  (GitLab). Перед удалением обязательно `git merge-base --is-ancestor
  <branch> master` — никакой потери коммитов.
- Ветка без активной задачи — мусор; чистится при ближайшей консолидации.

## Worktree

- Worktree разрешён для параллельной работы по задачам.
- Ветка worktree закрывается вместе с закрытием issue: worktree удаляется
  (`git worktree remove`), затем ветка.
- Мёртвые worktree-записи чистятся через `git worktree prune`.

## Stash-бэкапы

- Stash-бэкапы (ветки вида `busNNN-stash-backup-*`) — **local-only**: не пушить
  в ремоуты. Они не являются частью истории продукта и удаляются локально,
  когда задача закрыта.

## GitLab-зеркало

- После каждого мержа в master выполняется mirror-синк: `git push gitlab
  master:master` (fast-forward) — GitHub остаётся источником истины,
  GitLab — резервом.
- Новые feature-ветки пушатся в оба ремоута; удаление — тоже в оба.

## Чеклист закрытия задачи с веткой

1. Мерж в master (PR на GitHub) — CI зелёный.
2. `git merge-base --is-ancestor <branch> master` — проверка перед удалением.
3. `git branch -d <branch>` локально; `git push origin --delete <branch>`;
   `git push gitlab --delete <branch>`.
4. `git worktree remove <path>` (если был worktree) или `git worktree prune`.
5. `git push gitlab master:master` — догнать зеркало.
6. В комментарии к issue: что удалено, что оставлено и почему.
