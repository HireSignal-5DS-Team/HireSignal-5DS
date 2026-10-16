import { useState } from "react";
import { ApiClient } from "./api";

interface KnowledgeReference {
  title: string;
  source_type: string;
  source_id: string;
  url: string | null;
  text: string;
  retrieval: string;
  score: number | null;
}
interface Inspection {
  query: string;
  category: string;
  provider: string;
  corpus_esco: number | null;
  elapsed_ms: number;
  retrieved: number;
  trace?: {
    gated?: boolean;
    terms?: Array<{ term: string; how: string }>;
  } | null;
  references: KnowledgeReference[];
}

export default function RagInspector() {
  const [term, setTerm] = useState("Python");
  const [category, setCategory] = useState("skill");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Inspection | null>(null);
  const [error, setError] = useState("");

  async function inspect() {
    if (!term.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await new ApiClient(undefined, 60000).ragInspect(term.trim(), category) as Inspection;
      if (!response || !Array.isArray(response.references) || typeof response.provider !== "string") {
        throw new Error("The RAG inspector returned an unexpected response.");
      }
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "RAG inspection failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel rag-inspector">
      <div className="panel-title">
        <div>
          <h2>Live RAG inspector</h2>
          <p>Test the actual ESCO knowledge retrieval used by the Matcher. No CV or candidate data is sent.</p>
        </div>
        <span className="badge">Read-only</span>
      </div>
      <form
        className="rag-controls"
        onSubmit={(event) => { event.preventDefault(); void inspect(); }}
      >
        <label>
          Requirement or skill to look up
          <input
            aria-label="RAG search term"
            maxLength={120}
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="e.g. Python"
          />
        </label>
        <label>
          Requirement category
          <select aria-label="RAG category" value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="skill">Skill</option>
            <option value="experience">Experience</option>
            <option value="education">Education (gated)</option>
            <option value="certification">Certification (gated)</option>
            <option value="language">Language (gated)</option>
          </select>
        </label>
        <button className="button primary" type="submit" disabled={loading || !term.trim()}>
          {loading ? "Retrieving…" : "Inspect RAG retrieval"}
        </button>
      </form>
      <p className="field-hint">
        Try <button className="rag-inline" type="button" onClick={() => { setTerm("Python"); setCategory("skill"); }}>Python</button>
        {" "}for a confirmed ESCO match, or{" "}
        <button className="rag-inline" type="button" onClick={() => { setTerm("SQL database development"); setCategory("skill"); }}>SQL database development</button>
        {" "}to see a cautious no-match. These are retrieval checks, not model predictions.
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      {result && (
        <div className="rag-results" aria-live="polite">
          <div className="rag-metrics">
            <span><strong>{result.provider}</strong> · retrieval engine</span>
            <span><strong>{result.corpus_esco ?? "—"}</strong> ESCO concepts</span>
            <span><strong>{result.elapsed_ms} ms</strong> lookup time</span>
            <span><strong>{result.retrieved}</strong> sources retrieved</span>
          </div>
          {result.trace?.gated && (
            <p className="notice">Skipped on purpose: the selected category is gated by this RAG configuration.</p>
          )}
          {result.trace?.terms?.map((entry, index) => (
            <p key={index} className="field-hint">
              Query: <strong>{entry.term}</strong> · selection method: <strong>{entry.how}</strong>
            </p>
          ))}
          {result.references.length === 0 && (
            <p className="notice">No knowledge passed the relevance filter. This is an intentional abstention, not proof that the skill is missing from a candidate's CV.</p>
          )}
          {result.references.map((reference) => (
            <div className="rag-source" key={reference.source_id}>
              <strong>{reference.title}</strong>
              <p>{reference.text}</p>
              <small>{reference.source_type.toUpperCase()} · {reference.retrieval}</small>
              {reference.url && /^https?:\/\//i.test(reference.url) && (
                <p><a href={reference.url} target="_blank" rel="noopener noreferrer">Open official source ↗</a></p>
              )}
            </div>
          ))}
          <p className="field-hint">RAG provides skill terminology to the Matcher; only actual CV evidence can support a MET decision.</p>
        </div>
      )}
    </section>
  );
}
