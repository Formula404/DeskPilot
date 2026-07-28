import { MouseEvent, useEffect, useMemo, useState } from "react";
import { Clipboard, ExternalLink, File, FileArchive, FileSpreadsheet, FileText, FolderSearch } from "lucide-react";
import { openArtifactFile, revealArtifactFile } from "../api/client";
import type { TaskArtifact } from "../types/api";
import { AppContextMenu, type AppContextMenuGroup } from "./AppContextMenu";

interface ArtifactMenuState {
  artifact: TaskArtifact;
  x: number;
  y: number;
}

function fileName(path: string) {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

function fileExtension(path: string) {
  const name = fileName(path);
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index + 1).toUpperCase() : "文件";
}

function ArtifactIcon({ path, type }: TaskArtifact) {
  const extension = fileExtension(path).toLowerCase();
  if (["xlsx", "xls", "csv"].includes(extension)) return <FileSpreadsheet size={17} />;
  if (["zip", "7z", "tar", "gz"].includes(extension) || type === "backup") return <FileArchive size={17} />;
  if (["md", "txt", "pdf", "docx"].includes(extension) || type === "knowledge_source") return <FileText size={17} />;
  return <File size={17} />;
}

export function ArtifactLinks({ artifacts, onError }: { artifacts: TaskArtifact[]; onError: (message: string) => void }) {
  const [menu, setMenu] = useState<ArtifactMenuState | null>(null);
  const items = useMemo(() => {
    const seen = new Set<string>();
    return artifacts.filter((artifact) => {
      if (!artifact.path || seen.has(artifact.path)) return false;
      seen.add(artifact.path);
      return true;
    });
  }, [artifacts]);

  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("pointerdown", close);
    window.addEventListener("blur", close);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("blur", close);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [menu]);

  if (!items.length) return null;

  async function open(artifact: TaskArtifact) {
    setMenu(null);
    try {
      await openArtifactFile(artifact.path);
    } catch (error) {
      onError(error instanceof Error ? error.message : "无法打开文件");
    }
  }

  async function reveal(artifact: TaskArtifact) {
    setMenu(null);
    try {
      await revealArtifactFile(artifact.path);
    } catch (error) {
      onError(error instanceof Error ? error.message : "无法在文件资源管理器中显示文件");
    }
  }

  async function copyPath(artifact: TaskArtifact) {
    setMenu(null);
    try {
      await navigator.clipboard.writeText(artifact.path);
    } catch {
      onError("无法复制文件路径，请检查系统剪贴板权限");
    }
  }

  function showMenu(event: MouseEvent<HTMLButtonElement>, artifact: TaskArtifact) {
    event.preventDefault();
    const menuWidth = 206;
    const menuHeight = 124;
    setMenu({
      artifact,
      x: Math.max(8, Math.min(event.clientX, window.innerWidth - menuWidth - 8)),
      y: Math.max(8, Math.min(event.clientY, window.innerHeight - menuHeight - 8))
    });
  }

  return (
    <section className="assistant-artifacts" aria-label="生成的文件">
      <span className="assistant-artifacts-heading">生成的文件</span>
      {items.map((artifact) => (
        <button
          key={`${artifact.type}:${artifact.path}`}
          className="assistant-artifact-link"
          title={`${artifact.path}\n单击打开，右键查看更多操作`}
          onClick={() => void open(artifact)}
          onContextMenu={(event) => showMenu(event, artifact)}
        >
          <span className="assistant-artifact-icon"><ArtifactIcon {...artifact} /></span>
          <span className="assistant-artifact-copy">
            <strong>{fileName(artifact.path)}</strong>
            <small>{fileExtension(artifact.path)} · 单击打开</small>
          </span>
          <ExternalLink size={14} />
        </button>
      ))}
      {menu ? (
        <AppContextMenu
          ariaLabel={`${fileName(menu.artifact.path)} 文件操作`}
          className="assistant-artifact-menu"
          groups={[
            {
              id: "file",
              items: [
                { id: "open", label: "打开文件", icon: <ExternalLink size={15} />, onSelect: () => open(menu.artifact) },
                { id: "reveal", label: "在文件资源管理器中显示", icon: <FolderSearch size={15} />, onSelect: () => reveal(menu.artifact) }
              ]
            },
            {
              id: "path",
              items: [
                { id: "copy-path", label: "复制文件路径", icon: <Clipboard size={15} />, onSelect: () => copyPath(menu.artifact) }
              ]
            }
          ] satisfies AppContextMenuGroup[]}
          style={{ left: menu.x, top: menu.y }}
          onPointerDown={(event) => event.stopPropagation()}
          onEscape={() => setMenu(null)}
        />
      ) : null}
    </section>
  );
}
