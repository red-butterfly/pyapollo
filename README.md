apollo-client - Python Client for Ctrip's Apollo
================

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

方便Python接入配置中心框架 [Apollo](https://github.com/ctripcorp/apollo) 所开发的Python版本客户端。
Tested with python 3

基于https://github.com/filamoon/pyapollo/ 修改

Installation
------------

``` shell
pip install apollo-client-py
```

# Features
* 实时同步配置
* 灰度配置
* 客户端容灾

# Usage

- 启动客户端长连接监听

``` python
from pyapollo import ApolloClient

client = ApolloClient(app_id=<appId>, cluster=<clusterName>, config_server_url=<configServerUrl>, secret=<app secret>)
client.start()
```

- 获取Apollo的配置
  ```
  client.get_value(Key, DefaultValue)
  ```

# Contribution
  * Source Code: https://github.com/BruceWW/pyapollo
  * Issue Tracker: https://github.com/BruceWW/pyapollo/issues
  * Original Source Code: https://github.com/filamoon/pyapollo
  
# License
The project is licensed under the [Apache 2 license](https://github.com/zouyx/agollo/blob/master/LICENSE).

# Reference
Apollo : https://github.com/ctripcorp/apollo

# Contributor
[Bruce](https://github.com/BruceWW)<br/>
[prchen](https://github.com/prchen) <br/>
[xhrg](https://github.com/faicm)<br/>


# Version log
11/24/2019  Bruce  0.8.2   优化本地缓存的存储方式<br/>
1/4/2020    Bruce  0.8.4   修复文件读取异常的bug<br/>
3/24/2020   [prchen](https://github.com/prchen) 0.8.5   修复安装过程中requests模块依赖的问题<br/>
7/5/2020    Bruce  0.9     主线程退出时，关闭获取配置的子线程<br/>
25/5/2020   [xhrg](https://github.com/faicm)    0.9.1   修复文件名称读取异常<br/>
