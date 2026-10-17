import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { CV_ACCEPT } from "./cv-files";
import { workflowStages } from "./workflow";
import RagInspector from "./RagInspector";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  Menu,
  Plus,
  Search,
  ShieldCheck,
  Signal,
  Sparkles,
  Upload,
  Users,
  X,
  Zap,
} from "lucide-react";
import {
  adapter,
  ApiClient,
  fileToB64,
  flow,
  MAX_TEXT,
  mode,
  readCVFile,
  sampleCV,
  sampleJob,
  seedCampaign,
  stages,
  validateInput,
} from "./api";
import type {
  AnalysisInput,
  Campaign,
  CandidateRecord,
  CV,
  Decision,
} from "./contracts";

type UpdateReview = (
  id: string,
  review: CandidateRecord["review"],
  note: string,
) => void;
const nav = [
  ["/", "Overview", LayoutDashboard],
  ["/analysis", "New analysis", Plus],
  ["/results", "Candidates", Users],
  ["/processing", "AI workflow", Activity],
  ["/reports", "Reports", FileText],
  ["/system", "System status", Signal],
] as const;
function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <FileText size={32} />
      <h3>{title}</h3>
      <p>{text}</p>
      <Link className="button primary" to="/analysis">
        <Plus size={16} />
        New analysis
      </Link>
    </div>
  );
}
function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
function Counts({ candidate }: { candidate: CandidateRecord }) {
  return (
    <div className="decision-counts">
      {(["MET", "UNCERTAIN", "MISSING"] as Decision[]).map((d) => (
        <span key={d} className={d.toLowerCase()} title={d}>
          <i />
          {candidate.report.summary.counts[d]} <small>{d.toLowerCase()}</small>
        </span>
      ))}
    </div>
  );
}
function CandidateTable({
  campaigns,
  limit,
}: {
  campaigns: Campaign[];
  limit?: number;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All reviews");
  const rows = campaigns
    .flatMap((c) =>
      c.candidates.map((candidate) => ({ campaign: c, candidate })),
    )
    .filter(
      ({ candidate, campaign }) =>
        `${candidate.label} ${campaign.title}`
          .toLowerCase()
          .includes(query.toLowerCase()) &&
        (filter === "All reviews" || candidate.review === filter),
    );
  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>{limit ? "Ready for your review" : "Candidate workspace"}</h2>
          <p>Evidence first. Every recommendation stays in your hands.</p>
        </div>
        {limit && (
          <Link className="text-link" to="/results">
            View all <ArrowRight size={15} />
          </Link>
        )}
      </div>
      {!limit && (
        <div className="table-tools">
          <label className="search">
            <Search size={17} />
            <input
              aria-label="Search candidates"
              placeholder="Search candidate or role…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Review filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            {[
              "All reviews",
              "Pending review",
              "Reviewed",
              "Follow-up needed",
            ].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Candidate</th>
              <th>Campaign</th>
              <th>Requirement signals</th>
              <th>Human review</th>
              <th>
                <span className="sr-only">Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(0, limit ?? rows.length)
              .map(({ campaign, candidate }, i) => (
                <tr key={candidate.id}>
                  <td>
                    <Link
                      className="candidate-name"
                      to={`/candidates/${candidate.id}`}
                    >
                      <span className={`avatar avatar-${i % 3}`}>
                        {candidate.label.slice(-2)}
                      </span>
                      <span>
                        {candidate.label}
                        <small>{campaign.mode} · anonymized profile</small>
                      </span>
                    </Link>
                  </td>
                  <td>
                    {campaign.title}
                    <small>
                      {new Date(campaign.created).toLocaleDateString("en-GB", {
                        day: "numeric",
                        month: "short",
                      })}
                    </small>
                  </td>
                  <td>
                    <Counts candidate={candidate} />
                  </td>
                  <td>
                    <Badge
                      tone={candidate.review === "Reviewed" ? "green" : "amber"}
                    >
                      {candidate.review}
                    </Badge>
                  </td>
                  <td>
                    <Link
                      className="icon-link"
                      aria-label={`Review ${candidate.label}`}
                      to={`/candidates/${candidate.id}`}
                    >
                      <ArrowRight size={18} />
                    </Link>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <div className="empty">
          <Search />
          <h3>No candidates found</h3>
          <p>Try another search or start a new analysis.</p>
        </div>
      )}
    </section>
  );
}
function Dashboard({ campaigns }: { campaigns: Campaign[] }) {
  const candidates = campaigns.flatMap((c) => c.candidates);
  const pending = candidates.filter((c) => c.review !== "Reviewed").length;
  return (
    <>
      <PageHeading
        eyebrow="YOUR RECRUITMENT WORKSPACE"
        title="Clarity for every hiring conversation."
        description="Turn candidate information into evidence you can actually review."
        action={
          <Link className="button primary" to="/analysis">
            <Plus size={17} />
            New analysis
          </Link>
        }
      />
      <section className="hero">
        <div className="hero-copy">
          <Badge tone="hero-badge">
            <Sparkles size={13} /> Evidence-led recruitment
          </Badge>
          <h2>
            See the evidence.
            <br />
            Keep the human perspective.
          </h2>
          <p>
            One transparent workflow, from CV to review.
            <br /> Understand the match, the gaps, and the questions to ask
            next.
          </p>
          <Link className="button light" to="/analysis">
            Start an analysis <ArrowRight size={16} />
          </Link>
        </div>
        <div className="signal-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <div className="signal-core">
            <Signal size={45} />
          </div>
          <div className="floating floating-one">
            <span className="mini-icon">
              <FileText size={17} />
            </span>
            <div>
              CV evidence<small>Grounded in the source</small>
            </div>
            <Check size={16} />
          </div>
          <div className="floating floating-two">
            <span className="mini-icon">
              <ShieldCheck size={17} />
            </span>
            <div>
              Human perspective<small>Built into every review</small>
            </div>
          </div>
          <span className="art-dot dot-one" />
          <span className="art-dot dot-two" />
        </div>
      </section>
      <div className="stats">
        {[
          [ClipboardCheck, "Campaigns", campaigns.length, "In this session"],
          [
            Users,
            "Candidates analyzed",
            candidates.length,
            mode === "MOCK" ? "Demonstration profiles" : "Completed analyses",
          ],
          [CircleAlert, "Awaiting review", pending, "Your next conversations"],
          [
            ShieldCheck,
            "Reviews completed",
            candidates.length - pending,
            "Human-reviewed records",
          ],
        ].map(([Icon, label, value, caption]) => {
          const StatIcon = Icon as typeof Users;
          return (
            <section className="stat" key={String(label)}>
              <div>
                <span>{String(label)}</span>
                <StatIcon size={19} />
              </div>
              <strong>{String(value).padStart(2, "0")}</strong>
              <small>{String(caption)}</small>
            </section>
          );
        })}
      </div>
      <div className="dashboard-grid">
        <section className="panel campaigns">
          <div className="panel-title">
            <div>
              <h2>Active campaigns</h2>
              <p>A clear view of your current searches.</p>
            </div>
            <Badge>{campaigns.length} total</Badge>
          </div>
          {campaigns.length ? (
            campaigns.map((c) => (
              <Link
                key={c.id}
                to={`/results?campaign=${c.id}`}
                className="campaign-row"
              >
                <span className="role-icon">
                  <BarChart3 size={21} />
                </span>
                <div>
                  <h3>{c.title}</h3>
                  <p>
                    {c.candidates.length} candidates <span>·</span> {c.mode}{" "}
                    analysis
                  </p>
                </div>
                <div className="campaign-status">
                  <Badge tone="green">Analysis complete</Badge>
                  <ChevronRight size={17} />
                </div>
              </Link>
            ))
          ) : (
            <Empty
              title="Your first campaign starts here"
              text="Add a role and candidate text to begin."
            />
          )}
        </section>
        <section className="principle-card">
          <span className="principle-icon">
            <ShieldCheck size={25} />
          </span>
          <span className="eyebrow">RESPONSIBLE BY DESIGN</span>
          <h2>
            More context.
            <br />
            Less assumption.
          </h2>
          <p>
            Missing evidence is a question to explore, never a reason to
            automatically reject.
          </p>
          <Link className="text-link" to="/reports">
            Explore the review process <ArrowRight size={15} />
          </Link>
        </section>
      </div>
      <CandidateTable campaigns={campaigns} limit={4} />
      <div className="bottom-note">
        <ShieldCheck size={15} /> AI assists. People decide. No automated hiring
        decisions.
      </div>
    </>
  );
}
function NewAnalysis({
  onStart,
  initial,
}: {
  onStart: (input: AnalysisInput) => void;
  initial: AnalysisInput | null;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [text, setText] = useState("");
  const [candidates, setCandidates] = useState<CV[]>(initial?.candidates ?? []);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [readProgress, setReadProgress] = useState("");
  const uploadController = useRef<AbortController | null>(null);
  useEffect(() => () => uploadController.current?.abort(), []);
  const [confirmed, setConfirmed] = useState(false);
  function addText() {
    if (!text.trim()) {
      setError("Paste CV text before adding a candidate.");
      return;
    }
    if (candidates.length >= 10) {
      setError("You can analyze up to 10 candidates at a time.");
      return;
    }
    setCandidates([
      ...candidates,
      { cv_id: crypto.randomUUID(), text, structured: {} },
    ]);
    setText("");
    setError("");
  }
  async function upload(files: FileList | null) {
    if (!files?.length || uploadController.current) return;
    const controller = new AbortController();
    uploadController.current = controller;
    setReading(true);
    setConfirmed(false);
    setError("");
    try {
      if (candidates.length + files.length > 10)
        throw new Error("You can analyze up to 10 candidates at a time.");
      const failures: string[] = [];
      for (const file of Array.from(files)) {
        if (controller.signal.aborted) break;
        setReadProgress(`Reading ${file.name}…`);
        try {
          const extracted = await readCVFile(
            file,
            (message) => setReadProgress(`${file.name} · ${message}`),
            controller.signal,
          );
          if (controller.signal.aborted) break;
          // V2: the original file also goes to the server-side Reader (browser text is a preview only).
          const structured =
            mode === "REAL" && flow === "v2"
              ? { source_file: { name: file.name, b64: await fileToB64(file) } }
              : {};
          setCandidates((prev) => [
            ...prev,
            { cv_id: crypto.randomUUID(), text: extracted, structured },
          ]);
        } catch (e) {
          failures.push((e as Error).message);
        }
      }
      setError(failures.join("\n"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setReading(false);
      setReadProgress("");
      uploadController.current = null;
    }
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    if (reading) return;
    setError("");
    try {
      const all = text.trim()
        ? [...candidates, { cv_id: crypto.randomUUID(), text, structured: {} }]
        : candidates;
      const input = { title, description, candidates: all };
      validateInput(input);
      if (!confirmed)
        throw new Error(
          "Confirm that you removed identifying and sensitive personal information.",
        );
      onStart(input);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="FROM INFORMATION TO INSIGHT"
        title="Start with the right context."
        description="Define the role, add anonymized CVs, and let the review begin."
      />
      <div className="analysis-layout">
        <form onSubmit={submit} className="analysis-form">
          <section className="panel form-panel">
            <div className="step-title">
              <span>01</span>
              <div>
                <h2>Define the role</h2>
                <p>Give every candidate the same requirements.</p>
              </div>
              <button
                className="button subtle"
                type="button"
                onClick={() => {
                  setTitle("Frontend Engineer");
                  setDescription(sampleJob);
                  setText(sampleCV);
                  setError("");
                }}
              >
                Use sample
              </button>
            </div>
            <label>
              Role title
              <input
                required
                maxLength={120}
                placeholder="e.g. Frontend Engineer"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              Job description / requirements
              <textarea
                required
                rows={7}
                maxLength={MAX_TEXT}
                placeholder={
                  mode === "REAL" && flow === "v2"
                    ? "Paste a complete job description. The Job Agent extracts required and preferred qualifications."
                    : "Add one requirement per line…\nReact\nTypeScript\nAccessible interfaces"
                }
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <p className="field-hint">
              {mode === "REAL" && flow === "v2"
                ? "In REAL V2, the Job Agent reads this whole description and extracts must-have and preferred requirements with evidence."
                : "In DEMO, each non-empty line becomes one must-have requirement. No AI extraction is performed."}
            </p>
          </section>
          <section className="panel form-panel">
            <div className="step-title">
              <span>02</span>
              <div>
                <h2>Add candidate CVs</h2>
                <p>Up to 10 anonymized profiles per analysis.</p>
              </div>
              <Badge>{candidates.length} added</Badge>
            </div>
            <label className="upload-zone">
              <Upload size={26} />
              <strong>
                {reading ? "Extracting CV text…" : "Choose CV files"}
              </strong>
              <span>PDF, PNG, JPG, WebP · up to 10 MB · TXT up to 200 KB</span>
              <input
                aria-label="Upload CV files"
                type="file"
                accept={CV_ACCEPT}
                multiple
                disabled={reading}
                onChange={(e) => {
                  void upload(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
            {reading && (
              <div className="attached">
                <span role="status">{readProgress}</span>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => uploadController.current?.abort()}
                >
                  Cancel extraction
                </button>
              </div>
            )}
            <p className="field-hint">
              PDFs support up to 10 pages. Images and scanned pages use English
              OCR in your browser; OCR assets download on first use. Review
              extracted text below and remove personal details before analysis.
              Maximum 50,000 characters per CV. DOCX is not supported.
            </p>
            <label>
              Or paste CV content
              <textarea
                rows={6}
                maxLength={MAX_TEXT}
                placeholder="Paste anonymized experience, skills, and qualifications…"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <button
              className="button secondary"
              type="button"
              onClick={addText}
              disabled={reading}
            >
              <Plus size={16} />
              Add this candidate
            </button>
            {candidates.map((c, i) => (
              <div key={c.cv_id}>
                <div className="attached">
                  <FileText size={18} />
                  <span>
                    Candidate {String(i + 1).padStart(2, "0")}
                    <small>
                      {c.text.length.toLocaleString()} characters · text ready
                    </small>
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove candidate ${i + 1}`}
                    className="icon-link"
                    disabled={reading}
                    onClick={() =>
                      setCandidates(
                        candidates.filter((x) => x.cv_id !== c.cv_id),
                      )
                    }
                  >
                    <X size={17} />
                  </button>
                </div>
                <details className="source-text">
                  <summary>
                    Review / edit Candidate {String(i + 1).padStart(2, "0")}{" "}
                    text
                  </summary>
                  <label>
                    Extracted text for Candidate {i + 1}
                    <textarea
                      rows={7}
                      maxLength={MAX_TEXT}
                      disabled={reading}
                      value={c.text}
                      onChange={(e) => {
                        setCandidates((prev) =>
                          prev.map((item) =>
                            item.cv_id === c.cv_id
                              ? { ...item, text: e.target.value }
                              : item,
                          ),
                        );
                        setConfirmed(false);
                      }}
                    />
                  </label>
                  <p className="field-hint">
                    Check reading order and OCR accuracy. This edited text
                    becomes the evidence source.
                  </p>
                </details>
              </div>
            ))}
          </section>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I removed names, contact details and sensitive personal information
            from the CVs.
          </label>
          {error && (
            <div role="alert" className="error">
              <CircleAlert size={18} />
              {error}
            </div>
          )}
          <div className="form-footer">
            <span>
              {mode === "MOCK"
                ? "Text stays in this session in MOCK mode."
                : "REAL mode: text is sent to the local FastAPI backend only."}
            </span>
            <button
              className="button primary"
              disabled={reading}
              type="submit"
            >
              <Sparkles size={17} />
              Run {mode === "MOCK" ? "demo analysis" : "analysis"}
            </button>
          </div>
        </form>
        <aside className="analysis-aside">
          <div className="panel">
            <span className="eyebrow">A TRANSPARENT WORKFLOW</span>
            <h2>Every step has a purpose.</h2>
            <ol className="mini-pipeline">
              {stages.map((s, i) => (
                <li key={s}>
                  <span>{i + 1}</span>
                  {s}
                </li>
              ))}
            </ol>
            <div className="aside-note">
              <ShieldCheck size={19} />
              <p>
                These are workflow responsibilities, not seven separate models.
              </p>
            </div>
          </div>
          <div className="notice">
            <strong>
              {mode === "MOCK"
                ? "You’re in demonstration mode"
                : "REAL mode — live local backend"}
            </strong>
            <p>
              {mode === "MOCK"
                ? "Progress and requirement decisions are simulated. No model, retrieval, Judge or fairness audit runs."
                : "Candidates are processed serially through POST /api/v1/match on the configured backend. Matcher, gated RAG, Bias Auditor and NLI Judge all run."}
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
function Processing({
  input,
  running,
  step,
  error,
  campaign,
  retry,
}: {
  input: AnalysisInput | null;
  running: boolean;
  step: number;
  error: string;
  campaign: Campaign | null;
  retry: () => void;
}) {
  const verifiedStages = workflowStages(mode, campaign, running, step, error, flow);
  return (
    <>
      <PageHeading
        eyebrow="UNDER THE HOOD"
        title="An explainable path to review."
        description="Follow the responsibilities that turn candidate text into a structured report."
      />
      {!input ? (
        <Empty
          title="No analysis in progress"
          text="Start an analysis to see the workflow here."
        />
      ) : (
        <section className="panel processing">
          <div className="processing-header">
            <div className="processing-symbol">
              <Activity size={28} />
            </div>
            <h2>
              {error
                ? "Analysis could not complete"
                : running
                  ? mode === "REAL" ? "Running real analysis…" : "Preparing your demo report…"
                  : "Your analysis is ready for review."}
            </h2>
            <p>
              {input.title} · {input.candidates.length} candidate
              {input.candidates.length === 1 ? "" : "s"}
            </p>
            <Badge tone={mode === "REAL" ? "green" : "amber"}>
              {mode === "REAL" ? "REAL · backend results" : "MOCK / DEMO · simulated progress"}
            </Badge>
          </div>
          <div className="pipeline" aria-live="polite">
            {verifiedStages.map(({ name, state, detail }, i) => (
              <div key={name} className={`pipeline-step ${state.toLowerCase().replace(/ /g, "-")}`}>
                <span>{state === "Completed" ? <Check size={18} /> : i + 1}</span>
                <div>
                  <strong>{name}</strong>
                  <small>{detail}</small>
                </div>
                <Badge tone={state === "Completed" ? "green" : state === "Failed" ? "red" : state === "Not integrated" ? "amber" : ""}>
                  {state}
                </Badge>
              </div>
            ))}
          </div>
          {error ? (
            <>
              <div className="error" role="alert">
                {error}
              </div>
              <button className="button secondary" onClick={retry}>
                Retry analysis
              </button>
            </>
          ) : !running && campaign ? (
            <Link
              className="button primary"
              to={`/results?campaign=${campaign.id}`}
            >
              Review candidate evidence <ArrowRight size={17} />
            </Link>
          ) : (
            <p className="muted">
              {mode === "REAL"
                ? flow === "v2"
                  ? "Awaiting FastAPI results. Reader, Profile, Job Agent, Matcher and Reporter run on the server; their real stage statuses appear on each candidate when it finishes."
                  : "Awaiting FastAPI results. No per-stage progress is available from the API."
                : "You can navigate elsewhere while this demo completes."}
            </p>
          )}
        </section>
      )}
    </>
  );
}
function Detail({
  campaigns,
  onReview,
}: {
  campaigns: Campaign[];
  onReview: UpdateReview;
}) {
  const { id } = useParams();
  const campaign = campaigns.find((c) => c.candidates.some((p) => p.id === id));
  const candidate = campaign?.candidates.find((c) => c.id === id);
  const [note, setNote] = useState(candidate?.note ?? "");
  const [review, setReview] = useState<CandidateRecord["review"]>(
    candidate?.review ?? "Pending review",
  );
  const [saved, setSaved] = useState(false);
  if (!candidate || !campaign)
    return (
      <Empty
        title="Candidate not available"
        text="Records are kept in memory for this session. Start an analysis after a page refresh."
      />
    );
  return (
    <>
      <Link className="back-link" to="/results">
        <ArrowLeft size={16} />
        All candidates
      </Link>
      <PageHeading
        eyebrow={`${campaign.mode} ANALYSIS`}
        title={candidate.label}
        description={`${campaign.title} · Anonymized candidate profile`}
        action={<Badge tone="amber">{candidate.review}</Badge>}
      />
      <div className="detail-summary">
        <div>
          <span className="eyebrow">
            REQUIREMENT SIGNALS{" "}
            {campaign.mode === "MOCK" ? "· SIMULATED" : "· LIVE BACKEND"}
          </span>
          <Counts candidate={candidate} />
        </div>
        <p>
          No fit score is assigned. Requirement decisions are review aids, not a
          hiring recommendation.
        </p>
      </div>
      <div className="detail-layout">
        <div>
          <section className="panel">
            <div className="panel-title">
              <div>
                <h2>Requirement-by-requirement evidence</h2>
                <p>
                  Quotes come from the submitted text. Interpretation remains
                  unverified.
                </p>
              </div>
            </div>
            <div className="requirements">
              {candidate.report.results.map((r) => (
                <article className="requirement" key={r.req_id}>
                  <div className="requirement-title">
                    <h3>{r.requirement_text}</h3>
                    <Badge
                      tone={
                        r.decision === "MET"
                          ? "green"
                          : r.decision === "MISSING"
                            ? "red"
                            : "amber"
                      }
                    >
                      {r.decision}
                    </Badge>
                  </div>
                  <span className="eyebrow">
                    {r.kind === "must" ? "MUST HAVE" : "NICE TO HAVE"} ·{" "}
                    {r.basis.replaceAll("_", " ")}
                  </span>
                  {r.evidence.length ? (
                    r.evidence.map((quote, i) => (
                      <blockquote key={i}>
                        {quote}
                        <cite>
                          CV source · character span [{r.evidence_spans[i][0]},{" "}
                          {r.evidence_spans[i][1]})
                        </cite>
                      </blockquote>
                    ))
                  ) : (
                    <div className="no-evidence">
                      No exact evidence found. Ask the candidate for
                      clarification.
                    </div>
                  )}
                  <p>{r.explanation}</p>
                  {(r.review_reasons?.length ?? 0) > 0 && (
                    <small className="review-reasons">
                      <strong>Review flags:</strong> {r.review_reasons.join("; ")}
                    </small>
                  )}
                  <small>
                    Knowledge shown to Matcher:{" "}
                    {r.rag_refs.length
                      ? `${r.rag_refs.length} source(s)`
                      : campaign.mode === "MOCK"
                        ? "None — DEMO, no retrieval"
                        : "0 sources — strict RAG filter abstained"}
                  </small>
                  {campaign.mode === "REAL" && (
                    <details className="rag-trace">
                      <summary>Inspect model & RAG retrieval trace</summary>
                      <p><strong>Model:</strong> {r.provenance?.served_alias ?? "Not reported"}</p>
                      <p><strong>Answered by:</strong> {r.provenance?.answered_by ?? "Not reported"} · <strong>Prompt:</strong> {r.provenance?.prompt_id ?? "Not reported"}</p>
                      <p><strong>Knowledge provider:</strong> {r.provenance?.knowledge_provider ?? "Not reported"}</p>
                      {typeof r.matcher_call?.latency_s === "number" && (
                        <p><strong>Matcher inference:</strong> {r.matcher_call.latency_s.toFixed(2)} seconds · finish: {r.matcher_call.finish_reason ?? "Not reported"}</p>
                      )}
                      {r.citations?.length ? (
                        r.citations.map((source) => (
                          <div className="rag-source" key={source.source_id}>
                            <strong>{source.title}</strong>
                            <p><small>{source.source_type} · {source.retrieval}</small></p>
                            {source.url?.startsWith("https://") && (
                              <a href={source.url} target="_blank" rel="noopener noreferrer">View source ↗</a>
                            )}
                          </div>
                        ))
                      ) : <p>No ESCO knowledge passed the filter for this requirement. The Matcher still uses CV evidence.</p>}
                    </details>
                  )}
                  {campaign.mode === "REAL" && (
                    <div className="per-req-audit">
                      <Badge
                        tone={
                          r.judge
                            ? r.judge.judge_verdict === "PASS"
                              ? "green"
                              : r.judge.judge_verdict === "FAIL"
                                ? "red"
                                : "amber"
                            : ""
                        }
                      >
                        Judge: {r.judge?.judge_verdict ?? "Not executed"}
                      </Badge>
                      <Badge
                        tone={
                          r.bias_audit?.audit_status === "PASS"
                            ? "green"
                            : r.bias_audit?.audit_status === "FLAGGED"
                              ? "red"
                              : ""
                        }
                      >
                        Bias: {r.bias_audit?.audit_status ?? "Not executed"}
                      </Badge>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
          {candidate.stages && (
            <section className="panel">
              <div className="panel-title">
                <div>
                  <h2>Pipeline stages (actual)</h2>
                  <p>What the server really ran for this candidate. A failed stage is never shown as a success.</p>
                </div>
              </div>
              <div className="requirements">
                {candidate.stages.map((s) => (
                  <div className="requirement" key={s.stage}>
                    <strong>{s.stage}</strong>{" "}
                    <Badge tone={s.status === "ok" ? "green" : "red"}>{s.status}</Badge>
                    <small>
                      {s.elapsed_s != null ? ` ${s.elapsed_s} s` : ""}
                      {s.error ? ` · ${s.error}` : ""}
                    </small>
                  </div>
                ))}
              </div>
              {!!candidate.upstream?.review_reasons?.length && (
                <p className="field-hint">
                  HUMAN REVIEW REQUIRED (upstream): {candidate.upstream.review_reasons.join(", ")}
                </p>
              )}
            </section>
          )}
          {candidate.reporter && (
            <section className="panel">
              <div className="panel-title">
                <div>
                  <h2>Validated Report Writer</h2>
                  <p>
                    Grounded summary and requirement notes. Every SLM-written section
                    is checked against the verified pipeline facts.
                  </p>
                </div>
              </div>
              {!!candidate.upstream?.review_reasons?.length && (
                <p className="field-hint" role="alert">
                  HUMAN REVIEW REQUIRED for upstream checks: {candidate.upstream.review_reasons.join(", ")}.
                  These flags are additional to the per-requirement review count in the generated summary.
                </p>
              )}
              <p>{candidate.reporter.executive_summary.text}</p>
              <p className="field-hint">
                Summary writer: {candidate.reporter.executive_summary.writer} ·
                SLM: {candidate.reporter.provenance.sections_slm}/
                {candidate.reporter.provenance.sections_total} sections accepted ·
                Fallback: {candidate.reporter.provenance.sections_fallback} ·
                Status: {candidate.reporter.provenance.slm_status}
              </p>
              <div className="requirements">
                {candidate.reporter.requirements.map((item) => (
                  <div className="requirement" key={item.req_id}>
                    <strong>{item.req_id}</strong>
                    <p>{item.plain_note.text}</p>
                    <small>Writer: {item.plain_note.writer}</small>
                  </div>
                ))}
              </div>
            </section>
          )}
          <details className="panel source-text">
            <summary>Inspect original CV text</summary>
            <pre>{candidate.cv.text}</pre>
          </details>
        </div>
        <aside className="detail-aside">
          <section className="panel">
            <ShieldCheck className="teal" size={25} />
            <h2>Verification & fairness</h2>
            {(() => {
              const judges = candidate.report.results.map((r) => r.judge?.judge_verdict).filter(Boolean) as string[];
              const biases = candidate.report.results.map((r) => r.bias_audit?.audit_status).filter(Boolean) as string[];
              const judgeModel = candidate.report.results.find((r) => r.judge)?.judge?.model;
              const anyFlag = (vs: string[], neg: string[]) => vs.some((v) => neg.includes(v));
              const judgeTone = judges.length
                ? anyFlag(judges, ["FAIL"])
                  ? "red"
                  : anyFlag(judges, ["UNCERTAIN"])
                    ? "amber"
                    : "green"
                : "";
              const biasTone = biases.length
                ? anyFlag(biases, ["FLAGGED"])
                  ? "red"
                  : "green"
                : "";
              return (
                <>
                  <div className="review-check">
                    <strong>Judge verification</strong>
                    <Badge tone={judgeTone}>
                      {judges.length
                        ? `${judges.filter((v) => v === "PASS").length} PASS · ${judges.filter((v) => v === "FAIL").length} FAIL · ${judges.filter((v) => v === "UNCERTAIN").length} UNCERTAIN`
                        : "Not executed"}
                    </Badge>
                    <p>
                      {judges.length
                        ? `NLI entailment check (${judgeModel}). FAIL/UNCERTAIN requirements are flagged for human review; they never become automatic rejections.`
                        : "No NLI or independent model verification ran in this demo."}
                    </p>
                  </div>
                  <div className="review-check">
                    <strong>Bias Auditor</strong>
                    <Badge tone={biasTone}>
                      {biases.length
                        ? `${biases.filter((v) => v === "PASS").length} PASS · ${biases.filter((v) => v === "FLAGGED").length} FLAGGED${biases.filter((v) => v === "NOT_TESTED").length ? ` · ${biases.filter((v) => v === "NOT_TESTED").length} NOT_TESTED` : ""}`
                        : "Not executed"}
                    </Badge>
                    <p>
                      {biases.length
                        ? "Rules-based auditor (rules_v2) over the matcher output; flags protected-attribute mentions and proxy signals per requirement."
                        : "Fairness is not established. Check for irrelevant personal attributes, proxy signals, and uneven evidence standards."}
                    </p>
                  </div>
                  <div className="notice">
                    <strong>Recommended next step</strong>
                    <p>
                      Review every requirement and seek clarification on
                      missing or uncertain evidence.{" "}
                      {campaign.mode === "MOCK"
                        ? "Do not use simulated outcomes to select or reject a candidate."
                        : "Automated decisions are review aids; never auto-reject."}
                    </p>
                  </div>
                </>
              );
            })()}
          </section>
          <section className="panel">
            <h2>Your review</h2>
            <p>Record your review without changing the original analysis.</p>
            <label>
              Review status
              <select
                value={review}
                onChange={(e) => {
                  setReview(e.target.value as CandidateRecord["review"]);
                  setSaved(false);
                }}
              >
                {["Pending review", "Reviewed", "Follow-up needed"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              Reviewer notes
              <textarea
                rows={4}
                maxLength={5000}
                placeholder="What should be clarified in a conversation?"
                value={note}
                onChange={(e) => {
                  setNote(e.target.value);
                  setSaved(false);
                }}
              />
            </label>
            <button
              className="button primary full"
              onClick={() => {
                onReview(candidate.id, review, note);
                setSaved(true);
              }}
            >
              <Check size={16} />
              Save review
            </button>
            <p className="field-hint" role="status">
              {saved
                ? "Review saved for this session. Export a report to keep it."
                : "Reviews are session-only; refreshing clears them."}
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
function exportReport(campaign: Campaign) {
  const artifact = {
    product: "HireSignal",
    exported_at: new Date().toISOString(),
    data_classification: "DEMO — not model output",
    evidence:
      "Verbatim quotes from submitted text; interpretations are simulated, not verified.",
    judge: "Not executed",
    fairness: "Not audited",
    human_review: "Session-local reviewer annotations; not a hiring decision",
    campaign,
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(artifact, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `hiresignal-${campaign.id}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function Reports({ campaigns }: { campaigns: Campaign[] }) {
  return (
    <>
      <PageHeading
        eyebrow="THE FULL PICTURE"
        title="Reports with a clear paper trail."
        description="Inspect the evidence, separate interpretation, and record the human perspective."
      />
      <div className="report-principles">
        {[
          ["01", "Source evidence", "Exact CV text and quote offsets."],
          ["02", "Interpretation", "Real model decisions or clearly labeled demo outputs."],
          ["03", "Human review", "Your notes, separately recorded."],
        ].map(([n, title, text]) => (
          <div key={n}>
            <span>{n}</span>
            <h3>{title}</h3>
            <p>{text}</p>
          </div>
        ))}
      </div>
      {!campaigns.length ? (
        <Empty
          title="No reports yet"
          text="Complete an analysis to generate a report."
        />
      ) : (
        <div className="report-list">
          {campaigns.map((c) => (
            <section className="panel report-card" key={c.id}>
              <div className="report-icon">
                <FileText size={26} />
              </div>
              <div>
                <Badge tone={c.mode === "REAL" ? "green" : "amber"}>{c.mode === "REAL" ? "REAL / LIVE BACKEND" : "MOCK / DEMO"}</Badge>
                <h2>{c.title}</h2>
                <p>
                  {c.candidates.length} candidate reports ·{" "}
                  {c.candidates.filter((p) => p.review !== "Reviewed").length}{" "}
                  awaiting review
                </p>
                <small>
                  {c.mode === "MOCK" ? "Source evidence + simulated interpretation + human annotations" : "Real evidence, Judge and Bias findings, plus a verified report where available"}
                </small>
              </div>
              <div className="report-actions">
                <Link
                  className="button secondary"
                  to={`/results?campaign=${c.id}`}
                >
                  View evidence <ArrowRight size={16} />
                </Link>
                <button
                  className="button subtle"
                  onClick={() => exportReport(c)}
                >
                  <ArrowDownToLine size={16} />
                  Export JSON
                </button>
              </div>
            </section>
          ))}
        </div>
      )}
      <div className="notice report-notice">
        <ShieldCheck size={21} />
        <div>
          <strong>Export includes submitted CV text and reviewer notes.</strong>
          <p>
            Keep exported files in an appropriate secure location. No
            server-side audit trail or persistence is configured.
          </p>
        </div>
      </div>
    </>
  );
}
function SystemStatus() {
  const [state, setState] = useState<
    Record<string, { data?: unknown; error?: string }>
  >({});
  const [loading, setLoading] = useState(false);
  async function check() {
    setLoading(true);
    const api = new ApiClient();
    const result = await Promise.allSettled([
      api.health(),
      api.ready(),
      api.models(),
    ]);
    setState(
      Object.fromEntries(
        result.map((r, i) => [
          ["Health", "Readiness", "Model status"][i],
          r.status === "fulfilled"
            ? { data: r.value }
            : { error: r.reason.message },
        ]),
      ),
    );
    setLoading(false);
  }
  return (
    <>
      <PageHeading
        eyebrow="CONNECTED SERVICES"
        title="Know what is actually running."
        description="Workflow agents describe responsibilities. The backend reports the underlying shared models."
        action={
          <button
            className="button primary"
            disabled={loading}
            onClick={() => void check()}
          >
            <Activity size={16} />
            {loading ? "Checking…" : "Check backend"}
          </button>
        }
      />
      <div className="notice">
        <strong>Execution mode: {mode}</strong>
        <p>
          {mode === "MOCK"
            ? "No model runs in the demo. Service checks below call the configured backend only when requested."
            : "REAL matching is live: the Analysis page calls POST /api/v1/match on the configured backend. Use the checks below to inspect readiness and model provenance."}
        </p>
      </div>
      <div className="system-grid">
        {["Health", "Readiness", "Model status"].map((s, i) => (
          <section className="panel" key={s}>
            <Signal className="teal" />
            <h2>{s}</h2>
            <code>
              {["GET /health", "GET /ready", "GET /api/v1/models/status"][i]}
            </code>
            <div aria-live="polite">
              {state[s]?.error ? (
                <p className="error" role="alert">
                  {state[s].error}
                </p>
              ) : state[s]?.data ? (
                <>
                  <Badge tone="green">
                    Response received · raw service data
                  </Badge>
                  <pre>{JSON.stringify(state[s].data, null, 2)}</pre>
                </>
              ) : (
                <p>Not checked. No service status is assumed.</p>
              )}
            </div>
          </section>
        ))}
      </div>
      {mode === "REAL" && <RagInspector />}
    </>
  );
}
function Results({ campaigns }: { campaigns: Campaign[] }) {
  const location = useLocation();
  const campaignId = new URLSearchParams(location.search).get("campaign");
  const selected = campaignId
    ? campaigns.filter((c) => c.id === campaignId)
    : campaigns;
  return (
    <>
      <PageHeading
        eyebrow="EVIDENCE, NOT ASSUMPTIONS"
        title="Make the next conversation count."
        description="Review requirement signals, inspect source evidence, and decide what to explore next."
        action={
          <Link className="button primary" to="/analysis">
            <Plus size={17} />
            New analysis
          </Link>
        }
      />
      {campaignId && (
        <Link className="back-link" to="/results">
          <ArrowLeft size={16} />
          Show all campaigns
        </Link>
      )}
      {selected.length ? (
        <CandidateTable campaigns={selected} />
      ) : (
        <Empty
          title="No candidate results yet"
          text="Run an analysis to see candidate evidence here."
        />
      )}
      <div className="notice report-notice">
        <CircleAlert size={20} />
        <p>
          <strong>MISSING means not documented.</strong> It does not prove a
          candidate lacks a skill. All demonstration results need human
          verification.
        </p>
      </div>
    </>
  );
}
export default function App() {
  const [campaigns, setCampaigns] = useState<Campaign[]>(() =>
    mode === "MOCK" ? [seedCampaign()] : [],
  );
  const [input, setInput] = useState<AnalysisInput | null>(null);
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [lastCampaign, setLastCampaign] = useState<Campaign | null>(null);
  const [menu, setMenu] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const busy = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    document.querySelector("main")?.focus();
    window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
    },
    [],
  );
  function start(next: AnalysisInput) {
    if (busy.current) {
      navigate("/processing");
      return;
    }
    busy.current = true;
    setInput(next);
    setRunning(true);
    setStep(0);
    setError("");
    setLastCampaign(null);
    navigate("/processing");
    const execute = () => {
      void adapter
        .run(next)
        .then((c) => {
          setCampaigns((prev) => [c, ...prev]);
          setLastCampaign(c);
        })
        .catch((e) => setError(e instanceof Error ? e.message : "Analysis failed."))
        .finally(() => {
          setRunning(false);
          busy.current = false;
        });
    };
    if (timer.current) clearInterval(timer.current);
    if (mode === "REAL") {
      // REAL requests start immediately. The API does not stream stage progress.
      execute();
    } else {
      let current = 0;
      timer.current = setInterval(() => {
        current++;
        if (current < stages.length) {
          setStep(current);
        } else {
          if (timer.current) clearInterval(timer.current);
          execute();
        }
      }, 450);
    }
  }
  function updateReview(
    id: string,
    review: CandidateRecord["review"],
    note: string,
  ) {
    setCampaigns((prev) =>
      prev.map((c) => ({
        ...c,
        candidates: c.candidates.map((p) =>
          p.id === id ? { ...p, review, note } : p,
        ),
      })),
    );
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <Link className="brand" to="/" onClick={() => setMenu(false)}>
          <span>
            <Signal size={25} />
          </span>
          HireSignal<span className="brand-dot">.</span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-icon">H</span>
          <div>
            Hiring workspace<small>Recruitment intelligence</small>
          </div>
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {nav.map(([path, label, Icon]) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              onClick={() => setMenu(false)}
            >
              <Icon size={19} />
              {label}
              {path === "/processing" && running && (
                <span className="running-dot" />
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={22} />
            <strong>Built for better judgment.</strong>
            <p>
              Explainable signals.
              <br />
              Human decisions.
            </p>
          </div>
          <div className="user-info">
            <span className="avatar">HR</span>
            <div>
              Recruiter workspace<small>Session-only demo</small>
            </div>
            <span className="online-dot" />
          </div>
        </div>
      </aside>
      {menu && (
        <button
          aria-label="Close navigation"
          className="menu-backdrop"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-toggle icon-link"
              aria-label="Toggle navigation"
              aria-expanded={menu}
              onClick={() => setMenu(!menu)}
            >
              <Menu size={22} />
            </button>
            <span className="breadcrumb">
              Workspace <ChevronRight size={14} />{" "}
              <strong>
                {nav.find(([p]) => p === location.pathname)?.[1] ??
                  "Candidate detail"}
              </strong>
            </span>
          </div>
          <div className="topbar-right">
            <Badge tone="green">
              <span className="online-dot" />
              {mode === "MOCK" ? "Demo workspace" : "REAL configuration"}
            </Badge>
            <span className="top-avatar">HR</span>
          </div>
        </header>
        <div className="mode-banner">
          <Zap size={14} />
          <span>
            <strong>
              {mode === "MOCK" ? "MOCK / DEMO" : "REAL · live backend"}
            </strong>{" "}
            {mode === "MOCK"
              ? "Simulated analysis. No live AI models. Data and reviews reset on refresh."
              : "Candidates are matched on the local FastAPI backend. Reviews reset on refresh."}
          </span>
        </div>
        <main id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Dashboard campaigns={campaigns} />} />
            <Route
              path="/analysis"
              element={
                running ? (
                  <>
                    <PageHeading
                      eyebrow="ANALYSIS IN PROGRESS"
                      title={mode === "REAL" ? "Your real analysis is running." : "Your demo is running."}
                      description="Finish this analysis before starting another."
                    />
                    <Link className="button primary" to="/processing">
                      View progress <ArrowRight size={16} />
                    </Link>
                  </>
                ) : (
                  <NewAnalysis onStart={start} initial={input} />
                )
              }
            />
            <Route
              path="/processing"
              element={
                <Processing
                  input={input}
                  running={running}
                  step={step}
                  error={error}
                  campaign={lastCampaign}
                  retry={() => input && start(input)}
                />
              }
            />
            <Route
              path="/results"
              element={<Results campaigns={campaigns} />}
            />
            <Route
              path="/candidates/:id"
              element={
                <Detail
                  key={location.pathname}
                  campaigns={campaigns}
                  onReview={updateReview}
                />
              }
            />
            <Route
              path="/reports"
              element={<Reports campaigns={campaigns} />}
            />
            <Route path="/system" element={<SystemStatus />} />
            <Route
              path="*"
              element={
                <Empty
                  title="This page could not be found"
                  text="Use the workspace navigation or start a new analysis."
                />
              }
            />
          </Routes>
        </main>
        <footer>
          HireSignal{" "}
          <span>Thoughtful technology. Better-informed conversations.</span>
          <span>Human review required</span>
        </footer>
      </div>
    </div>
  );
}
