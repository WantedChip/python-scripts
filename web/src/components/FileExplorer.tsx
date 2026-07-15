"use client";

import React, { useState, useEffect } from "react";
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  BookOpen,
  ChevronRight,
  ChevronDown,
  Menu,
  X,
  Loader2,
  AlertCircle,
  Terminal,
} from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { FileNode } from "@/lib/search/types";

interface FileExplorerProps {
  fileTree: FileNode[];
  scriptPath: string;
  scriptName: string;
  initialFilePath?: string;
}

export default function FileExplorer({
  fileTree,
  scriptPath,
  initialFilePath,
}: FileExplorerProps) {
  // Find a default selected file (README.md or mainFile)
  const findDefaultFile = (nodes: FileNode[]): string | null => {
    // Try to find README.md first
    const readme = findFileByName(nodes, "README.md");
    if (readme) return readme;

    // Fallback: first .py file in list
    const pyFile = findFileByExtension(nodes, ".py");
    if (pyFile) return pyFile;

    // Fallback: first actual file in tree
    return findFirstFile(nodes);
  };

  const findFileByName = (nodes: FileNode[], name: string): string | null => {
    for (const node of nodes) {
      if (node.type === "file" && node.name.toLowerCase() === name.toLowerCase()) {
        return node.path;
      }
      if (node.type === "dir" && node.children) {
        const found = findFileByName(node.children, name);
        if (found) return found;
      }
    }
    return null;
  };

  const findFileByExtension = (nodes: FileNode[], ext: string): string | null => {
    for (const node of nodes) {
      if (node.type === "file" && node.name.toLowerCase().endsWith(ext)) {
        return node.path;
      }
      if (node.type === "dir" && node.children) {
        const found = findFileByExtension(node.children, ext);
        if (found) return found;
      }
    }
    return null;
  };

  const findFirstFile = (nodes: FileNode[]): string | null => {
    for (const node of nodes) {
      if (node.type === "file") return node.path;
      if (node.type === "dir" && node.children) {
        const found = findFirstFile(node.children);
        if (found) return found;
      }
    }
    return null;
  };

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  const [fileData, setFileData] = useState<
    Record<string, { content: string; html: string; lang: string }>
  >({});
  const [loadingPath, setLoadingPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Parse initial file settings
  useEffect(() => {
    const defaultFile = initialFilePath || findDefaultFile(fileTree);
    if (defaultFile) {
      setSelectedPath(defaultFile);
      // Automatically expand parent folders of the selected file
      const parts = defaultFile.split("/");
      if (parts.length > 1) {
        const newExpanded: Record<string, boolean> = { ...expandedDirs };
        let currentPath = "";
        for (let i = 0; i < parts.length - 1; i++) {
          currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i];
          newExpanded[currentPath] = true;
        }
        setExpandedDirs(newExpanded);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileTree, initialFilePath]);

  // Load file content when selection changes
  useEffect(() => {
    if (!selectedPath) return;
    
    const fetchContent = async () => {
      // Return early if cached
      if (fileData[selectedPath]) return;

      setLoadingPath(selectedPath);
      setError(null);

      try {
        const response = await fetch(
          `/api/file-content?path=${encodeURIComponent(`${scriptPath}/${selectedPath}`)}`
        );
        if (!response.ok) {
          throw new Error(`Failed to load file contents: ${response.statusText}`);
        }
        const data = await response.json();
        setFileData((prev) => ({
          ...prev,
          [selectedPath]: {
            content: data.content,
            html: data.highlightedHtml,
            lang: data.lang,
          },
        }));
      } catch (err: unknown) {
        console.error(err);
        const message = err instanceof Error ? err.message : "Error reading file content.";
        setError(message);
      } finally {
        setLoadingPath(null);
      }
    };

    fetchContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPath, scriptPath]);

  // File icons picker
  const getFileIcon = (fileName: string) => {
    const lower = fileName.toLowerCase();
    if (lower === "readme.md") return <BookOpen className="h-4 w-4 text-[var(--accent)] shrink-0" />;
    if (lower.endsWith(".py")) return <FileCode className="h-4 w-4 text-[var(--warning)] shrink-0" />;
    if (lower.endsWith(".txt")) return <FileText className="h-4 w-4 text-[var(--text-muted)] shrink-0" />;
    return <FileText className="h-4 w-4 text-[var(--text-dim)] shrink-0" />;
  };

  const toggleDirectory = (dirPath: string) => {
    setExpandedDirs((prev) => ({
      ...prev,
      [dirPath]: !prev[dirPath],
    }));
  };

  // Render tree item node recursively
  const renderTreeNodes = (nodes: FileNode[], depth = 0) => {
    return nodes.map((node) => {
      const isDir = node.type === "dir";
      const isExpanded = expandedDirs[node.path];
      const isSelected = selectedPath === node.path;

      if (isDir) {
        return (
          <div key={node.path} className="flex flex-col">
            <button
              onClick={() => toggleDirectory(node.path)}
              style={{ paddingLeft: `${depth * 12 + 8}px` }}
              className="flex items-center gap-1.5 w-full text-left py-1.5 hover:bg-[var(--surface-hover)] rounded-md transition-colors text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text)] cursor-pointer"
            >
              {isExpanded ? (
                <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-dim)]" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-dim)]" />
              )}
              {isExpanded ? (
                <FolderOpen className="h-4 w-4 shrink-0 text-[var(--accent)]" />
              ) : (
                <Folder className="h-4 w-4 shrink-0 text-[var(--accent)]" />
              )}
              <span className="truncate">{node.name}</span>
            </button>
            
            {isExpanded && node.children && (
              <div className="flex flex-col">
                {renderTreeNodes(node.children, depth + 1)}
              </div>
            )}
          </div>
        );
      }

      // File item click trigger
      return (
        <button
          key={node.path}
          onClick={() => {
            setSelectedPath(node.path);
            setSidebarOpen(false); // Close mobile drawer
          }}
          style={{ paddingLeft: `${depth * 12 + 24}px` }}
          className={`flex items-center gap-2 w-full text-left py-1.5 rounded-md transition-all text-xs font-mono cursor-pointer ${
            isSelected
              ? "bg-[var(--accent-subtle)] text-[var(--text)] border-l-2 border-[var(--accent)] pl-[22px] font-semibold"
              : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-hover)]"
          }`}
        >
          {getFileIcon(node.name)}
          <span className="truncate flex-1">{node.name}</span>
          {node.size !== undefined && (
            <span className="text-[9px] text-[var(--text-dim)] pr-2 shrink-0">
              {(node.size / 1024).toFixed(1)}k
            </span>
          )}
        </button>
      );
    });
  };

  const activeData = selectedPath ? fileData[selectedPath] : null;
  const isReadme = selectedPath?.toLowerCase().endsWith(".md");

  return (
    <div className="flex flex-col bg-[var(--surface)] overflow-hidden h-full w-full">
      {/* Mobile Top Header */}
      <div className="flex md:hidden items-center justify-between px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
        <div className="flex items-center gap-2 text-xs font-mono text-[var(--text)]">
          <Terminal className="h-4 w-4 text-[var(--accent)]" />
          <span className="font-bold truncate max-w-[200px]">
            {selectedPath ? selectedPath.split("/").pop() : "Explorer"}
          </span>
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-1 rounded bg-[var(--surface)] border border-[var(--border)] text-[var(--text-muted)] cursor-pointer"
        >
          {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      <div className="flex-1 flex relative overflow-hidden">
        {/* Left Sidebar: Collapsible File Tree */}
        <div
          className={`absolute md:relative inset-y-0 left-0 z-20 w-64 border-r border-[var(--border)] bg-[var(--surface-raised)] flex flex-col transition-transform duration-200 ease-in-out md:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
          }`}
        >
          {/* Header titles */}
          <div className="px-4 py-3 border-b border-[var(--border-subtle)] shrink-0 flex items-center justify-between">
            <span className="text-xs font-bold font-mono text-[var(--text-dim)] uppercase tracking-wider">
              File Explorer
            </span>
          </div>

          {/* Node lists */}
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-0.5 scrollbar">
            {renderTreeNodes(fileTree)}
          </div>
        </div>

        {/* Backdrop for mobile tree drawer */}
        {sidebarOpen && (
          <div
            onClick={() => setSidebarOpen(false)}
            className="absolute inset-0 z-10 bg-black/50 md:hidden"
          />
        )}

        {/* Right Content Pane: Code View / Markdown Renderer */}
        <div className="flex-1 flex flex-col overflow-hidden bg-[var(--bg)]">
          {/* Path Breadcrumb bar */}
          <div className="px-4 py-2 bg-[var(--surface-raised)] border-b border-[var(--border-subtle)] font-mono text-[10px] text-[var(--text-dim)] shrink-0 truncate">
            <span>pyscripts</span>
            <span className="mx-1">/</span>
            <span>{scriptPath}</span>
            <span className="mx-1">/</span>
            <span className="text-[var(--text-muted)]">{selectedPath || ""}</span>
          </div>

          {/* Viewport */}
          <div className="flex-1 overflow-y-auto p-4 scrollbar">
            {loadingPath ? (
              // Loading State
              <div className="h-full flex flex-col gap-3 items-center justify-center text-xs text-[var(--text-dim)] font-mono">
                <Loader2 className="h-6 w-6 animate-spin text-[var(--accent)]" />
                <span>[pyscripts] loading file content...</span>
              </div>
            ) : error ? (
              // Error State
              <div className="h-full flex flex-col gap-3 items-center justify-center text-xs text-[var(--danger)] font-mono">
                <AlertCircle className="h-6 w-6" />
                <span>Error: {error}</span>
              </div>
            ) : activeData ? (
              isReadme ? (
                // Markdown Renderer (README.md)
                <div className="w-full py-2 markdown-content">
                  <MarkdownRenderer content={activeData.content} />
                </div>
              ) : (
                // Shiki Syntax Highlighted Code
                <div
                  dangerouslySetInnerHTML={{ __html: activeData.html }}
                  className="shiki-view text-xs leading-relaxed font-mono"
                />
              )
            ) : (
              // Empty selection fallback
              <div className="h-full flex items-center justify-center text-xs text-[var(--text-dim)] font-mono">
                Select a file from the explorer sidebar to begin reading.
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* CSS adjustments for Shiki output layout inside global stylesheet context */}
      <style>{`
        .shiki-view pre {
          background-color: transparent !important;
          margin: 0 !important;
          padding: 0 !important;
          overflow-x: auto;
        }
        .shiki-view code {
          font-family: var(--font-mono) !important;
          background: transparent !important;
          padding: 0 !important;
          border: none !important;
        }
      `}</style>
    </div>
  );
}
