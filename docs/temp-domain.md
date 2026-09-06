# 使用 Cloudflare Quick Tunnel 申请临时域名

Cloudflare Quick Tunnel 通常免费，不需要购买域名，也通常不需要账号，适合临时测试邮件验证和密码重置链接。

启动本地服务后，运行：

```bash
cloudflared tunnel --url http://localhost:3000
```

命令会输出一个临时公网地址，例如：

```text
https://xxxxx.trycloudflare.com
```

将该地址设置为：

```env
AUTH_PUBLIC_BASE_URL=https://xxxxx.trycloudflare.com
```

该地址仅在 Quick Tunnel 进程运行期间有效；停止隧道或重新启动后，地址通常会失效或发生变化。若需要长期稳定的公网地址，请购买域名并配置正式的 Cloudflare Tunnel。
