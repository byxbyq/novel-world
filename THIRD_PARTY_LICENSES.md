# 第三方依赖许可清单（THIRD_PARTY LICENSES）

> 本项目「小说世界」发布包中包含的第三方开源软件及其许可证。
> 全部依赖均为宽松许可证（MIT / BSD / Apache-2.0 / MPL / ZPL / PSF），
> 无 GPL 传染性协议，可安全用于商业分发。
>
> 生成方式：`pip-licenses --format=markdown --order=license --with-urls`
> 基线：requirements.lock（2026-08-10 冻结），Python 3.11 / Windows

## 许可证汇总

| 许可证 | 数量 | 代表依赖 |
|---|---|---|
| MIT 系 | 19 | PyYAML、flask-cors、urllib3、pydantic |
| BSD 系 | 12 | Flask、Werkzeug、Jinja2、numpy、httpx |
| Apache-2.0 | 6 | openai、requests、cryptography |
| MPL-2.0 | 2 | certifi、tqdm（tqdm 为 MPL-2.0 OR MIT 双许可） |
| 其他宽松 | 2 | waitress（ZPL）、typing_extensions（PSF-2.0） |

## 完整清单

| Name | Version | License | URL |
|---|---|---|---|
| distro | 1.9.0 | Apache Software License | https://github.com/python-distro/distro |
| openai | 2.53.0 | Apache Software License | https://github.com/openai/openai-python |
| requests | 2.34.2 | Apache Software License | https://github.com/psf/requests |
| sniffio | 1.3.1 | Apache Software License; MIT License | https://github.com/python-trio/sniffio |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| cryptography | 50.0.0 | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| Jinja2 | 3.1.6 | BSD License | https://github.com/pallets/jinja/ |
| colorama | 0.4.6 | BSD License | https://github.com/tartley/colorama |
| httpx | 0.28.1 | BSD License | https://github.com/encode/httpx |
| itsdangerous | 2.2.0 | BSD License | https://github.com/pallets/itsdangerous/ |
| Flask | 3.1.3 | BSD-3-Clause | https://github.com/pallets/flask/ |
| MarkupSafe | 3.0.3 | BSD-3-Clause | https://github.com/pallets/markupsafe/ |
| Werkzeug | 3.1.8 | BSD-3-Clause | https://github.com/pallets/werkzeug/ |
| click | 8.4.2 | BSD-3-Clause | https://github.com/pallets/click/ |
| httpcore | 1.0.9 | BSD-3-Clause | https://www.encode.io/httpcore/ |
| idna | 3.18 | BSD-3-Clause | https://github.com/kjd/idna |
| psutil | 7.2.2 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| pycparser | 3.0 | BSD-3-Clause | https://github.com/eliben/pycparser |
| python-dotenv | 1.2.2 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org |
| annotated-types | 0.8.0 | MIT | https://github.com/annotated-types/annotated-types |
| anyio | 4.14.2 | MIT | https://anyio.readthedocs.io/en/stable/versionhistory.html |
| charset-normalizer | 3.4.9 | MIT | https://github.com/jawah/charset_normalizer |
| flask-cors | 6.0.5 | MIT | https://corydolphin.github.io/flask-cors/ |
| jiter | 0.16.0 | MIT | https://github.com/pydantic/jiter/ |
| pydantic | 2.13.4 | MIT | https://github.com/pydantic/pydantic |
| pydantic_core | 2.46.4 | MIT | https://github.com/pydantic |
| typing-inspection | 0.4.2 | MIT | https://github.com/pydantic/typing-inspection |
| urllib3 | 2.7.0 | MIT | https://github.com/urllib3/urllib3 |
| PyYAML | 6.0.3 | MIT License | https://pyyaml.org/ |
| blinker | 1.9.0 | MIT License | https://github.com/pallets-eco/blinker/ |
| h11 | 0.16.0 | MIT License | https://github.com/python-hyper/h11 |
| cffi | 2.1.1 | MIT-0 | https://cffi.readthedocs.io/en/latest/whatsnew.html |
| tqdm | 4.70.0 | MPL-2.0 AND MIT（双许可，按 MIT 使用） | https://tqdm.github.io |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi |
| typing_extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| waitress | 3.0.2 | Zope Public License | https://github.com/Pylons/waitress |

## 说明

- `certifi`（MPL-2.0）：仅以证书捆绑包形式使用，不修改其源码，符合 MPL 要求。
- `tqdm`：双许可，本项目按 MIT 条款使用。
- 各许可证全文可在对应依赖的官方仓库 LICENSE 文件中获取，
  打包发布时可通过 `pip-licenses --with-license-file` 随包附带全文。
