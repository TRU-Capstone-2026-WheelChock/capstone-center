
# from typing import Mapping

# class ConfigError(RuntimeError):
#     pass

# def requre(config: Mapping[str, any], *keys: str)->any:
#     cur: any = config
#     path = ".".join(keys)
#     for k in keys:
#         if not isinstance(cur, Mapping) or k not in cur:
#             raise ConfigError(f"Missing required config: {path}")
#         cur = cur[k]
#     return cur