#!/usr/bin/env bash
# Fetch the GitHub numbers shown on the profile card and write build/stats.json.
# Needs an authenticated `gh` and `jq`.   Usage: build/fetch_stats.sh [login]
set -euo pipefail
unset GITHUB_TOKEN 2>/dev/null || true   # a stale token in the environment makes gh return 401
LOGIN="${1:-zanlazarevic}"
OUT="$(cd "$(dirname "$0")" && pwd)/stats.json"

user_json=$(gh api user)
followers=$(jq .followers <<<"$user_json")
created=$(jq -r .created_at <<<"$user_json")
node_id=$(jq -r .node_id <<<"$user_json")
commits=$(gh api "search/commits?q=author:$LOGIN" --jq .total_count)
prs=$(gh api "search/issues?q=author:$LOGIN+is:pr" --jq .total_count)
repos=$(gh api 'user/repos?per_page=100&affiliation=owner,collaborator,organization_member' \
          --paginate --jq '.[] | select(.fork | not) | .full_name')

# Lines added/removed by $LOGIN on a repo's default branch.
# 1) REST contributor stats (fast, cached by GitHub; 202 = still computing, empty = repo has 10k+ commits)
# 2) fall back to paging the commit history through GraphQL
lines_rest() {
  local body='[]' resp status b
  for _ in $(seq 1 12); do
    resp=$(gh api -i "repos/$1/stats/contributors" 2>/dev/null || true)
    status=$(sed -n '1s#.*HTTP/[0-9.]* \([0-9]*\).*#\1#p' <<<"$resp")
    if [ "$status" = "202" ]; then sleep 5; continue; fi
    b=$(sed '1,/^[[:space:]]*$/d' <<<"$resp"); [ -n "$b" ] && body="$b"
    break
  done
  jq -r --arg l "$LOGIN" '[.[]? | select(.author.login==$l)] | "\([.[].weeks[].a] | add // 0) \([.[].weeks[].d] | add // 0)"' <<<"$body"
}
lines_graphql() {
  local owner=${1%/*} name=${1#*/} after="" a=0 d=0 page pa pd more
  while :; do
    args=(-F owner="$owner" -F name="$name" -F id="$node_id"); [ -n "$after" ] && args+=(-F after="$after")
    page=$(gh api graphql "${args[@]}" -f query='
      query($owner:String!,$name:String!,$id:ID!,$after:String){ repository(owner:$owner,name:$name){ defaultBranchRef{ target{ ... on Commit{
        history(first:100, author:{id:$id}, after:$after){ pageInfo{ hasNextPage endCursor } nodes{ additions deletions } } } } } } }' \
      --jq '.data.repository.defaultBranchRef.target.history // {nodes:[],pageInfo:{hasNextPage:false,endCursor:""}}
            | "\([.nodes[].additions] | add // 0) \([.nodes[].deletions] | add // 0) \(.pageInfo.hasNextPage) \(.pageInfo.endCursor // "")"')
    read -r pa pd more after <<<"$page"
    a=$((a + pa)); d=$((d + pd))
    [ "$more" = "true" ] || break
  done
  echo "$a $d"
}

add=0; del=0; contributed=0; langs='{}'
for repo in $repos; do
  read -r a d <<<"$(lines_rest "$repo")"
  if [ "$a" = 0 ] && [ "$d" = 0 ]; then read -r a d <<<"$(lines_graphql "$repo")"; fi
  add=$((add + a)); del=$((del + d))
  if [ $((a + d)) -gt 0 ]; then
    contributed=$((contributed + 1))
    l=$(gh api "repos/$repo/languages" 2>/dev/null || echo '{}')
    langs=$(printf '%s\n%s\n' "$langs" "$l" | jq -s 'reduce (.[] | to_entries[]) as $e ({}; .[$e.key] += $e.value)')
  fi
  echo "$repo  +$a  -$d" >&2
done

jq -n --arg login "$LOGIN" --argjson followers "$followers" --arg created "$created" \
      --argjson commits "$commits" --argjson prs "$prs" --argjson repos "$(wc -l <<<"$repos" | tr -d ' ')" \
      --argjson contributed "$contributed" --argjson add "$add" --argjson del "$del" --argjson langs "$langs" \
      --arg fetched "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '{login:$login, followers:$followers, created_at:$created, commits:$commits, pull_requests:$prs,
        repos:$repos, repos_contributed:$contributed, additions:$add, deletions:$del,
        languages:$langs, fetched_at:$fetched}' > "$OUT"
echo "wrote $OUT" >&2
