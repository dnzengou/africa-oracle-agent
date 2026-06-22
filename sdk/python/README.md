# africa-oracle (Python SDK)

```sh
pip install africa-oracle
```

```python
from africa_oracle import Client
c = Client()                                # uses AFRICA_ORACLE_URL or default
print(c.health())
print(c.hunt("mtn", "GH"))
print(c.feeds_quorum(min_providers=2))
```

```sh
afri-oracle health
afri-oracle hunt --provider mtn --country GH
afri-oracle quorum --min 2
```

Zero runtime deps. ARM64-native (pure Python). Set `AFRICA_ORACLE_URL` env var to point at your own deploy.

Bundled DevFlow skill for downstream agents:

```python
from africa_oracle import devflow_skill
print(devflow_skill())                      # markdown artifact
```
