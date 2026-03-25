### cleanup artifacts

1. Stop & remove containers
```bash
1. docker ps -a -q --filter "ancestor=$(docker images -q 'pddl-sandbox')" | xargs -r docker rm -f
```

2. Remove all pddl-sandbox images
```bash
docker images -q 'pddl-sandbox' | xargs -r docker rmi -f
```

3. Remove cached plugin installs
```bash
rm -rf ~/.claude-personal/plugins/cache/pddl-copilot-marketplace
rm -rf ~/.claude-personal/plugins/cache/temp_git_*
```