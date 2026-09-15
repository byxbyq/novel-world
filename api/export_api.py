"""导出 API：支持 txt / markdown / html 格式"""

import urllib.parse
from flask import Response

# ── 导出 API ──

def _get_export_data():
    """获取导出所需的基础数据（仅提取需要的字段，避免 deepcopy 卡死）"""
    chapters = engine.chapters
    if not chapters:
        return None, None, None
    world_name = engine.world.config.name if engine.world else "小说世界"
    # 只提取导出所需的字段，避免深拷贝复杂对象
    chapters_snapshot = []
    for ch in chapters:
        chapters_snapshot.append({
            "chapter": ch.get("chapter", 0) if isinstance(ch, dict) else getattr(ch, "chapter", 0),
            "title": ch.get("title", "") if isinstance(ch, dict) else getattr(ch, "title", ""),
            "narrative": ch.get("narrative", "") if isinstance(ch, dict) else getattr(ch, "narrative", ""),
        })
    # 收集角色信息
    char_info = []
    for c in getattr(engine, "_characters", []):
        info = {"name": getattr(c.config, "name", c.name) if hasattr(c, "config") else c.name}
        info["gender"] = getattr(c.config, "gender", "") if hasattr(c, "config") else ""
        info["age"] = getattr(c.config, "age", "") if hasattr(c, "config") else ""
        info["personality"] = getattr(c.config, "personality", "") if hasattr(c, "config") else ""
        info["goal"] = c.long_term_goal.description if hasattr(c, "long_term_goal") and c.long_term_goal else ""
        char_info.append(info)
    return world_name, chapters_snapshot, char_info


def _export_txt(world_name, chapters, char_info):
    """纯文本格式"""
    lines = []
    lines.append("《%s》" % world_name)
    lines.append("")
    if char_info:
        lines.append("【角色表】")
        for c in char_info:
            line = c["name"]
            if c["gender"]: line += "（%s）" % c["gender"]
            if c["age"]: line += " %s岁" % c["age"]
            if c["personality"]: line += " - %s" % c["personality"]
            if c["goal"]: line += " | 目标：%s" % c["goal"]
            lines.append(line)
        lines.append("")
        lines.append("=" * 40)
        lines.append("")
    for ch in chapters:
        title = ch.get("title", "")
        num = ch.get("chapter", 0)
        narrative = ch.get("narrative", "")
        lines.append("第%d章 %s" % (num, title))
        lines.append("")
        lines.append(narrative)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _export_md(world_name, chapters, char_info):
    """Markdown格式"""
    lines = []
    lines.append("# 《%s》" % world_name)
    lines.append("")
    if char_info:
        lines.append("## 角色表")
        lines.append("")
        lines.append("| 角色 | 性别 | 年龄 | 性格 | 目标 |")
        lines.append("|------|------|------|------|------|")
        for c in char_info:
            lines.append("| %s | %s | %s | %s | %s |" % (
                c["name"], c["gender"], c["age"], c["personality"], c["goal"]
            ))
        lines.append("")
        lines.append("---")
        lines.append("")
    for ch in chapters:
        title = ch.get("title", "")
        num = ch.get("chapter", 0)
        narrative = ch.get("narrative", "")
        lines.append("## 第%d章 %s" % (num, title))
        lines.append("")
        # 将正文段落转为markdown段落（双换行分段）
        for para in narrative.split("\n"):
            para = para.strip()
            if para:
                lines.append(para)
                lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _export_html(world_name, chapters, char_info):
    """HTML格式（带样式，可直接阅读）"""
    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>%s</title>
<style>
  body { max-width: 800px; margin: 40px auto; padding: 0 20px; font-family: "Noto Serif SC", "Source Han Serif", serif; font-size: 18px; line-height: 1.8; color: #333; background: #faf8f5; }
  h1 { text-align: center; font-size: 28px; margin-bottom: 8px; color: #1a1a1a; }
  .meta { text-align: center; color: #888; font-size: 14px; margin-bottom: 40px; }
  .char-table { width: 100%%; border-collapse: collapse; margin: 20px 0 40px 0; font-size: 15px; }
  .char-table th, .char-table td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
  .char-table th { background: #f0ece6; font-weight: 600; }
  .chapter-title { font-size: 22px; font-weight: 600; margin: 50px 0 20px 0; color: #2c2c2c; border-bottom: 2px solid #d4c9b8; padding-bottom: 8px; }
  .chapter-body { text-indent: 2em; }
  .chapter-body p { margin: 0.8em 0; text-indent: 2em; }
  .separator { text-align: center; color: #ccc; margin: 30px 0; letter-spacing: 8px; }
  .footer { text-align: center; color: #aaa; font-size: 13px; margin-top: 60px; padding-top: 20px; border-top: 1px solid #eee; }
</style>
</head>
<body>
""" % world_name)
    html_parts.append("<h1>《%s》</h1>" % world_name)
    total_chars = sum(len(ch.get("narrative", "")) for ch in chapters)
    html_parts.append('<div class="meta">%d 章 · 约 %d 字</div>' % (len(chapters), total_chars))

    if char_info:
        html_parts.append("<table class='char-table'>")
        html_parts.append("<tr><th>角色</th><th>性别</th><th>年龄</th><th>性格</th><th>目标</th></tr>")
        for c in char_info:
            html_parts.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                c["name"], c["gender"], c["age"], c["personality"], c["goal"]
            ))
        html_parts.append("</table>")

    for ch in chapters:
        title = ch.get("title", "")
        num = ch.get("chapter", 0)
        narrative = ch.get("narrative", "")
        html_parts.append('<div class="chapter-title">第%d章 %s</div>' % (num, title))
        html_parts.append('<div class="chapter-body">')
        for para in narrative.split("\n"):
            para = para.strip()
            if para:
                # Escape HTML
                para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append("<p>%s</p>" % para)
        html_parts.append("</div>")
        html_parts.append('<div class="separator">* * *</div>')

    html_parts.append('<div class="footer">导出自「小说世界」天道引擎</div>')
    html_parts.append("</body></html>")
    return "\n".join(html_parts)


@app.route("/api/export", methods=["GET"])
def api_export():
    """导出全部章节，支持 format=txt|md|html"""
    fmt = request.args.get("format", "txt").lower()
    # 仅在获取数据时持锁，格式化在锁外执行，避免与 DM 引擎死锁
    with _engine_lock:
        world_name, chapters, char_info = _get_export_data()
    if not chapters:
        return jsonify({"error": "没有章节可导出"}), 400

    if fmt == "md" or fmt == "markdown":
        text = _export_md(world_name, chapters, char_info)
        ext = "md"
        mime = "text/markdown; charset=utf-8"
    elif fmt == "html":
        text = _export_html(world_name, chapters, char_info)
        ext = "html"
        mime = "text/html; charset=utf-8"
    else:
        text = _export_txt(world_name, chapters, char_info)
        ext = "txt"
        mime = "text/plain; charset=utf-8"

    # RFC 5987 编码文件名，支持中文等非 ASCII 字符
    encoded_name = urllib.parse.quote("%s.%s" % (world_name, ext))
    return Response(
        text,
        mimetype=mime,
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % encoded_name},
    )
