### Poetry/Python

```bash
cp config.ini.sample config.ini  # Edit with your credentials
poetry install
python -m vtraty_pes_bot --config config.ini
```

### Docker run (Nix)

```bash
nix build .#docker-image && docker load < ./result
docker run --rm -it --env-file=.env -v $PWD/data:/usr/src/app/data \
    vtraty-pes-bot --config $CONFIG_PATH
```

### Nix build

```bash
nix run .#vtraty-pes-bot.lock
git add ./lock.x86_64-linux.json
nix build .#vtraty-pes-bot
```

### Docker Compose

```bash
mkdir data && cp config.ini.sample data/config.ini
# Build the Nix docker image first:
nix build .#docker-image && docker load < ./result
docker-compose up -d
```
