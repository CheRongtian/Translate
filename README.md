# Local Translate

本地文本翻译工具。程序自动识别源语言并翻译为简体中文，Vue 3 提供页面，FastAPI 提供本地接口，翻译与术语分析由本机 Ollama 完成。

## 主要功能

- 粘贴英文文本，或读取 TXT、PDF、DOCX、PNG、JPG、JPEG 文件。
- 从上下文中分析人名、地名、机构名、产品名、型号、缩写和专业术语。
- 指定译法留空时跳过该候选；填写后采用用户译法；也可以选择保留原文。
- 用户确认的术语会传入每个翻译段落，并在结果生成后执行大小写敏感的完整词替换。
- 翻译完成后可以增加术语并直接应用，也可以携带完整术语表重新翻译。
- 翻译过程使用 token 级流式输出，译文会在生成时持续显示。
- Ollama 模型在请求结束后保留 30 分钟，减少重复加载等待。
- 支持 JSON 术语表导入、结果复制和 TXT 下载。

## 模型配置

- 模型：`qwen2.5:14b`
- `temperature: 0`
- `num_ctx: 8192`
- Ollama 地址：`http://localhost:11434/api/generate`

正文翻译提示词位于：

```text
local_translate/prompts/translation.md
```

程序会在每次翻译时读取该文件，修改提示词后无需修改 Python 代码。

## 项目结构

```text
Local-Translate/
├── .gitignore
├── app.py
├── Dockerfile
├── backend/
│   ├── api.py
│   ├── schemas.py
│   ├── services.py
│   └── static.py
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── App.vue
│   │   ├── main.ts
│   │   └── style.css
│   ├── package.json
│   └── vite.config.ts
├── local_translate/
│   ├── config.py
│   ├── documents.py
│   ├── ollama_client.py
│   ├── terminology.py
│   ├── text_processing.py
│   ├── translation.py
│   └── prompts/
│       └── translation.md
└── requirements.txt
```

## 首次安装

安装 Python 依赖：

```bash
cd /Users/cherongtian/Desktop/Projects/Local-Translate
python3 -m pip install -r requirements.txt
```

安装并构建 Vue 前端：

```bash
cd /Users/cherongtian/Desktop/Projects/Local-Translate/frontend
npm install
npm run build
```

准备 Ollama 模型：

```bash
ollama pull qwen2.5:14b
```

图片 OCR 还需要本机安装 Tesseract。

## 启动

```bash
cd /Users/cherongtian/Desktop/Projects/Local-Translate
python3 app.py
```

服务启动后会自动打开：

```text
http://localhost:8000
```

## Dockerfile

Dockerfile 会先构建 Vue 页面，再将静态文件复制到 FastAPI 运行镜像。容器内默认通过 `host.docker.internal:11434` 访问宿主机 Ollama，并监听 `8000` 端口。

## 导入术语表

可以导入数组，或带有 `terms` 数组的 JSON：

```json
{
  "terms": [
    {
      "source": "Chojuro",
      "translation": "长十郎",
      "preserve": false
    },
    {
      "source": "CUDA",
      "translation": "",
      "preserve": true
    }
  ]
}
```
