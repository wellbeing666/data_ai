import type { ChangeEvent, FormEvent } from "react";
import { Button } from "antd";

import type { KnowledgeDocument, KnowledgeSearchResponse } from "../../types";
import { isBusy } from "./shared";

export function KnowledgeBasePage(props: {
  documents: KnowledgeDocument[];
  file: File | null;
  query: string;
  search: KnowledgeSearchResponse | null;
  busy: string;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onQueryChange: (value: string) => void;
  onUpload: (event: FormEvent) => void;
  onSearch: (event: FormEvent) => void;
  onDelete: (docId: string) => void;
}) {
  return (
    <div className="content-grid two">
      <section className="card">
        <div className="card-header"><div><h2>知识库</h2><p>上传业务规则、指标口径和报告写作要求，增强 RAG 检索。</p></div></div>
        <form className="upload-zone upload-zone-feature" onSubmit={props.onUpload}>
          <div className="upload-icon">K</div>
          <div className="upload-copy">
            <strong>{props.file?.name || "选择知识文档"}</strong>
            <span>上传业务规则、指标口径和报告写作要求，用于增强 RAG 检索。</span>
          </div>
          <div className="upload-actions">
            <label className="file-picker">
              选择文件
              <input type="file" onChange={props.onFileChange} />
            </label>
            <Button type="primary" htmlType="submit" loading={isBusy(props.busy)}>上传</Button>
          </div>
        </form>
        <div className="list">
          {props.documents.map((doc) => (
            <div className="list-row" key={doc.doc_id}>
              <div><strong>{doc.filename}</strong><span>{doc.chunk_count} 个片段 · {doc.indexed ? "已索引" : "未索引"}</span></div>
              <button type="button" onClick={() => props.onDelete(doc.doc_id)}>删除</button>
            </div>
          ))}
        </div>
      </section>
      <section className="card">
        <div className="card-header"><div><h2>知识检索</h2><p>验证文档是否能支持当前分析解释。</p></div></div>
        <form className="form-stack" onSubmit={props.onSearch}>
          <label>
            检索问题
            <textarea rows={4} value={props.query} onChange={(event) => props.onQueryChange(event.target.value)} />
          </label>
          <button className="button button-primary" type="submit" disabled={isBusy(props.busy)}>检索</button>
        </form>
        <div className="list">
          {(props.search?.results || []).map((item) => (
            <div className="list-row" key={`${item.doc_id}-${item.chunk_index}`}>
              <div><strong>{item.filename}</strong><span>{item.chunk}</span></div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
