# Day 4 — Retrieval-augmented generation over my own lab notes, fully inside k3s

Yesterday I finished with Ollama running as a Deployment in `si-lab`, using the GPU, keeping its models on the external drive, and reachable only from inside the cluster or through `kubectl port-forward`. Today's goal was to put something useful on top of that endpoint: a small retrieval-augmented generation (RAG) pipeline that answers questions about my own day 1 to day 3 notes.

By the end of the night I had an embedding model loaded next to the chat model, Postgres with the pgvector extension running as a StatefulSet, and a small worker pod that chunks my notes, stores their embeddings, and answers questions using only what the notes say. All three test questions came back with correct, grounded answers. Every piece runs on the lab host inside k3s. My terminal only sent `kubectl` commands.

## The lab at a glance

- **My terminal:** where I edit manifests and run `kubectl`. The Kubernetes API reaches it through the same SSH tunnel on port 6443 as on days 2 and 3.
- **Lab host:** a laptop running Ubuntu and single-node k3s `v1.36.4+k3s1`. The GPU is an NVIDIA laptop GPU with 4 GB of video memory. The `si-lab` namespace enforces the baseline Pod Security level.
- **Already running from day 3:** Ollama as a Deployment with a ClusterIP Service named `ollama` on port 11434, the GPU assigned through the `nvidia` runtime class, and models on the external drive through a static hostPath PersistentVolume. The chat model is `llama3.2:3b`.
- **Storage:** the internal NVMe drive, which backs k3s' default `local-path` storage class, and the external USB drive, formatted exFAT and mounted at `/mnt/ailab-data`.

Placeholders used below: `labuser` is the SSH user on the lab host, `<lab-lan-ip>` is its address on my home network, `labnode` is the Kubernetes node name, and `~/.kube/k3s-lab.yaml` is the kubeconfig on my terminal.

## Design decisions before deploying anything

**Reuse the same Ollama for embeddings.** Ollama can serve embedding models as well as chat models, so I didn't add a second model server. I pulled `nomic-embed-text` into the existing Deployment. It's 274 MB and produces 768-dimension embeddings.

**Two models on a 4 GB card.** Loading `llama3.2:3b` and `nomic-embed-text` together uses roughly 3.2 GB of the 4 GB of video memory. That fits, but it's tight, so Ollama may swap models in and out, and the first query after an ingest can be slower. I didn't measure the first-query time.

**pgvector rather than a dedicated vector database.** pgvector adds a vector column type and similarity operators to ordinary Postgres, so storing and searching embeddings is plain SQL. That matters for where this series is heading: SQL-backed MCP agents and lab data in the style of Dynamics 365 Finance & Operations, always lab data and never production. Learning one database that handles both relational data and vectors fits that goal better than adding a separate system.

**Postgres data on the internal NVMe, not the external drive.** The Postgres volume uses k3s' `local-path` storage class, which lives on the lab host's internal NVMe drive. The external drive is exFAT, which has no Linux file ownership or permissions, and Postgres needs both, along with reliable `fsync`. Model weights stay on the external drive because they're large files that are mostly read, which exFAT handles fine.

**A StatefulSet for the database.** A StatefulSet gives the pod a stable name (`pgvector-0`) and creates its PersistentVolumeClaim from a template, so the data volume follows the pod across restarts.

**The password lives only in a Kubernetes Secret.** It's generated randomly inside the `kubectl` command that creates the Secret, and referenced by name everywhere else. None of the manifests contain it, and k3s encrypts Secrets at rest because of the `--secrets-encryption` flag from day 2.

## Step 1: Check the cluster and pull the embedding model

With the tunnel open in its own tab, as on days 2 and 3, I checked the node and what was already running in `si-lab`. From my terminal:

```text
$ kubectl get nodes
NAME      STATUS   ROLES           AGE   VERSION
labnode   Ready    control-plane   17h   v1.36.4+k3s1
$ kubectl -n si-lab get pods
NAME                      READY   STATUS    RESTARTS   AGE
ollama-768d64b4c8-wqpq6   1/1     Running   0          13h
```

Only the day 3 Ollama pod was running. Next, I pulled the embedding model into that same Ollama and listed what it now holds:

```text
$ kubectl -n si-lab exec deploy/ollama -- ollama pull nomic-embed-text
pulling manifest 
pulling 970aa74c0a90:  99% ▕█████████████████ ▏ 272 MB/274 MB   61 MB/s      0s
verifying sha256 digest 
writing manifest 
success 
$ kubectl -n si-lab exec deploy/ollama -- ollama list
NAME                       ID              SIZE      MODIFIED       
nomic-embed-text:latest    0a109f422b47    274 MB    25 seconds ago    
llama3.2:3b                a80c4f17acd5    2.0 GB    13 hours ago      
```

The embedding model is 274 MB next to the 2.0 GB chat model. Like the chat model on day 3, it lands on the external drive through Ollama's PersistentVolumeClaim, so it survives pod restarts.

## Step 2: Create the database secret

From my terminal:

```text
$ kubectl -n si-lab create secret generic pgvector-auth \
> --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)"
secret/pgvector-auth created
```

`openssl rand -hex 24` generates 24 random bytes as hex, and the `$(...)` passes that straight into the Secret. The value never appeared on screen, and it isn't in this post or in any manifest.

## Step 3: Run Postgres with pgvector

I wrote `day-04-pgvector.yaml` with two objects, a Service and a StatefulSet. This is the whole file:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: pgvector
  namespace: si-lab
spec:
  type: ClusterIP
  selector: {app: pgvector}
  ports:
  - {port: 5432, targetPort: 5432}
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: pgvector
  namespace: si-lab
spec:
  serviceName: pgvector
  replicas: 1
  selector:
    matchLabels: {app: pgvector}
  template:
    metadata:
      labels: {app: pgvector}
    spec:
      containers:
      - name: postgres
        image: pgvector/pgvector:pg17
        ports:
        - containerPort: 5432
        env:
        - {name: POSTGRES_USER, value: rag}
        - {name: POSTGRES_DB, value: rag}
        - {name: PGDATA, value: /var/lib/postgresql/data/pgdata}
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef: {name: pgvector-auth, key: POSTGRES_PASSWORD}
        resources:
          requests: {cpu: 250m, memory: 512Mi}
          limits: {memory: 2Gi}
        readinessProbe:
          exec:
            command: ["pg_isready", "-U", "rag", "-d", "rag"]
          initialDelaySeconds: 5
          periodSeconds: 10
        volumeMounts:
        - {name: data, mountPath: /var/lib/postgresql/data}
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: local-path
      resources:
        requests:
          storage: 10Gi
```

A few details worth calling out.

- **The image.** `pgvector/pgvector:pg17` is Postgres 17 with the pgvector extension already built in.
- **`serviceName: pgvector`.** A StatefulSet has to name a governing Service, and this ties it to the `pgvector` Service above. Strictly speaking, the per-pod DNS names a StatefulSet can have (like `pgvector-0.pgvector`) only exist with a headless Service. Mine is an ordinary ClusterIP Service, which is fine here because clients only ever use the Service name `pgvector`.
- **Requests and limits.** The pod asks for a quarter of a CPU and 512 MiB of memory, and it can't grow past 2 GiB of memory. There's no CPU limit, so Postgres can use spare CPU when it's available. There's no runtime class and no GPU request, so it never competes with Ollama for the single GPU.
- **The `pg_isready` readiness probe.** `pg_isready` ships with Postgres and reports whether the server is accepting connections. Until it passes, the Service doesn't send traffic to the pod, so nothing tries to connect while Postgres is still initializing its data folder.
- **The volume claim template.** Instead of a claim I create by hand, the StatefulSet stamps out one claim per pod from this template. The claim is named after the template and the pod, `data-pgvector-0`. It asks the `local-path` storage class for 10Gi, and that storage class provisions a volume on the internal NVMe drive. The volume is mounted at `/var/lib/postgresql/data`, and `PGDATA` points at a `pgdata` subfolder inside it, which is the usual pattern for the Postgres image on a fresh volume.
- **The password.** It comes from the `pgvector-auth` Secret through `secretKeyRef`, so the manifest only holds the Secret's name.

Then I applied it and watched the pod come up. From my terminal:

```text
$ kubectl apply -f ~/ssi-platform/k8s/day-04-pgvector.yaml
$ kubectl -n si-lab get pods -w
service/pgvector created
statefulset.apps/pgvector created
NAME                      READY   STATUS    RESTARTS   AGE
ollama-768d64b4c8-wqpq6   1/1     Running   0          13h
pgvector-0                0/1     Pending   0          0s
pgvector-0                0/1     Pending   0          0s
pgvector-0                0/1     Pending   0          6s
pgvector-0                0/1     ContainerCreating   0          6s
pgvector-0                0/1     ContainerCreating   0          7s
pgvector-0                0/1     Running             0          12s
pgvector-0                1/1     Running             0          23s
pgvector-0                1/1     Running             0          23s
```

The pod sat in `Pending` for about six seconds, most likely while the local-path provisioner created its volume. It was `Running` at 12 seconds and became ready (`1/1`) at 23 seconds, once `pg_isready` passed.

Then the claims:

```text
$ kubectl -n si-lab get pvc
NAME              STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS     VOLUMEATTRIBUTESCLASS   AGE
data-pgvector-0   Bound    pvc-<uid>   10Gi       RWO            local-path       <unset>                 4m6s
ollama-models     Bound    ollama-models-pv                           200Gi      RWO            ailab-external   <unset>                 13h
```

This output shows the storage design in two lines. The database claim is on `local-path`, which is the internal NVMe drive, and its volume was created on demand with a generated `pvc-...` name. The model claim is on `ailab-external`, bound to the static `ollama-models-pv` from day 3, which points at the external drive. Both are `Bound`.

## Step 4: Create the extension, the table, and the index

From my terminal, I sent the SQL to `psql` inside the database pod as a heredoc, and ended it with two `psql` commands that describe the result: `\dx` lists installed extensions, and `\d chunks` describes the table.

```text
$ kubectl -n si-lab exec -i pgvector-0 -- psql -U rag -d rag <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
  id        bigserial PRIMARY KEY,
  source    text NOT NULL,
  chunk     text NOT NULL,
  embedding vector(768) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops);
\dx
\d chunks
SQL
CREATE EXTENSION
CREATE TABLE
CREATE INDEX
                             List of installed extensions
  Name   | Version |   Schema   |                     Description                      
---------+---------+------------+------------------------------------------------------
 plpgsql | 1.0     | pg_catalog | PL/pgSQL procedural language
 vector  | 0.8.6   | public     | vector data type and ivfflat and hnsw access methods
(2 rows)

                                Table "public.chunks"
  Column   |    Type     | Collation | Nullable |              Default               
-----------+-------------+-----------+----------+------------------------------------
 id        | bigint      |           | not null | nextval('chunks_id_seq'::regclass)
 source    | text        |           | not null | 
 chunk     | text        |           | not null | 
 embedding | vector(768) |           | not null | 
Indexes:
    "chunks_pkey" PRIMARY KEY, btree (id)
    "chunks_embedding_hnsw" hnsw (embedding vector_cosine_ops)
```

`-i` without `-t` passes my terminal's input to `psql` without allocating a TTY, which is what a heredoc needs. The quoted `'SQL'` marker stops my shell from touching anything inside it. `IF NOT EXISTS` makes the whole block safe to run again.

The output confirms each piece. The `vector` extension is version 0.8.6. `bigserial` shows up as a `bigint` column with a sequence default. All four columns are `not null`. The table has its primary key index plus the HNSW index.

Each row is one chunk of one Markdown file: `source` is the file name, `chunk` is the text, and `embedding` is its 768-number vector from `nomic-embed-text`. The HNSW index uses `vector_cosine_ops`, which matches the cosine distance operator `<=>` that the query script uses. With only a few dozen rows the index hardly matters, and I didn't check whether the query planner used it. It's there so the table is ready to grow.

## A change of plan: everything on the lab host

My first plan was to run the ingest and question scripts in a Python virtual environment on my terminal, talking to the cluster through two port-forwards: 11435 for Ollama and 15432 for Postgres. Partway through, I changed my mind. I want everything in this lab to live and run on the lab host, with my terminal only issuing `kubectl` commands. That means no virtual environment on my terminal and no working copies of scripts or data there.

That decision shaped the rest of the day. The notes had to be on the lab host, the scripts had to run in a pod, and the pod had to reach Ollama and Postgres by their cluster DNS names instead of through port-forwards.

## Step 5: Copy the notes to the lab host once

I copied the day 1 to day 3 Markdown files to the lab host a single time, as one zip file. From my terminal:

```bash
scp ~/Downloads/ssi-platform-docs.zip labuser@<lab-lan-ip>:~/
ssh labuser@<lab-lan-ip> 'mkdir -p /mnt/ailab-data/ai-ops-homelab/docs && python3 -m zipfile -e ~/ssi-platform-docs.zip /mnt/ailab-data/ai-ops-homelab/docs && ls -l /mnt/ailab-data/ai-ops-homelab/docs'
```

The second command runs on the lab host in one shot. It creates the folder on the external drive, extracts the zip with Python's built-in `zipfile` module, and lists the result:

```text
-rwxr-xr-x 1 labuser labuser  6008 Sep 25 11:56 day-01-host-hardening.md
-rwxr-xr-x 1 labuser labuser 12654 Sep 25 11:56 day-02-secure-k3s.md
-rwxr-xr-x 1 labuser labuser 14264 Sep 25 11:56 day-03-model-serving.md
```

The sizes match the originals: 6008, 12654, and 14264 bytes. Every file shows the same `rwxr-xr-x` mode, even though these are plain text files. That's the exFAT drive at work: it has no Linux permissions of its own, so every file gets the same mode and owner. It's harmless for read-only notes, and it's the same reason the database lives on the NVMe drive instead.

## Step 6: The rag-worker manifest

`day-04-rag-worker.yaml` has four objects: a static PersistentVolume and claim for the notes, a ConfigMap holding the two scripts, and a Deployment for the worker pod.

The notes are attached the same way the models were on day 3. The baseline Pod Security level rejects `hostPath` written directly into a pod spec, but it allows a pod to use a PersistentVolumeClaim, and the claim can be bound to a static hostPath volume:

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: rag-docs-pv
spec:
  capacity:
    storage: 5Gi
  accessModes: ["ReadWriteOnce"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ailab-external
  hostPath:
    path: /mnt/ailab-data/ai-ops-homelab/docs
    type: Directory
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: rag-docs
  namespace: si-lab
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: ailab-external
  volumeName: rag-docs-pv
  resources:
    requests:
      storage: 5Gi
```

The ConfigMap `rag-scripts` holds `ingest.py` and `ask.py` as two keys, so the scripts live in the cluster rather than in an image or on my terminal. The Deployment, in full:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rag-worker
  namespace: si-lab
spec:
  replicas: 1
  selector:
    matchLabels: {app: rag-worker}
  template:
    metadata:
      labels: {app: rag-worker}
    spec:
      containers:
      - name: worker
        image: python:3.12-slim
        command: ["sh", "-c", "pip install --no-cache-dir --quiet 'psycopg[binary]' requests && sleep infinity"]
        workingDir: /app
        env:
        - {name: OLLAMA_URL, value: "http://ollama.si-lab.svc.cluster.local:11434"}
        - {name: PG_DSN, value: "host=pgvector.si-lab.svc.cluster.local port=5432 dbname=rag user=rag"}
        - {name: DOCS_DIR, value: /docs}
        - {name: PYTHONUNBUFFERED, value: "1"}
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef: {name: pgvector-auth, key: POSTGRES_PASSWORD}
        resources:
          requests: {cpu: 100m, memory: 128Mi}
          limits: {memory: 512Mi}
        readinessProbe:
          exec:
            command: ["python", "-c", "import psycopg, requests"]
          initialDelaySeconds: 10
          periodSeconds: 10
        volumeMounts:
        - {name: scripts, mountPath: /app, readOnly: true}
        - {name: docs, mountPath: /docs, readOnly: true}
      volumes:
      - name: scripts
        configMap:
          name: rag-scripts
      - name: docs
        persistentVolumeClaim:
          claimName: rag-docs
```

A few details worth calling out. The container installs its two Python libraries when it starts and then sleeps, so it's a place to run scripts with `kubectl exec`, not a long-running service. The readiness probe only passes once those imports work, which tells me the install finished. Ollama and Postgres are reached by their cluster DNS names, and the password comes from the Secret through `PGPASSWORD`, which the Postgres client library reads on its own. Both mounts are read-only. The pod has no runtime class and no GPU request, so it never competes with Ollama for the single GPU. The embedding and generation work happens inside Ollama.

## Step 7: What the scripts do

**`ingest.py`** reads every `.md` file in `/docs`, splits each one into chunks, embeds the chunks with `nomic-embed-text`, and stores them in the `chunks` table.

Chunking works on paragraphs. It groups consecutive paragraphs until adding the next one would pass 1200 characters, then starts a new chunk. A paragraph is never split, so a single very long paragraph (such as a big code block) becomes a chunk on its own even if it's over the limit.

```python
MAX_CHARS = 1200

def chunk_markdown(text):
    """Group paragraphs into chunks of up to MAX_CHARS characters."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            chunks.append(current)
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current:
        chunks.append(current)
    return chunks
```

Each file's chunks go to Ollama's `/api/embed` endpoint in one request. `nomic-embed-text` expects a task prefix on its input, so stored text gets `search_document: ` and questions later get `search_query: `. Before inserting, the script deletes any existing rows for that file, which makes re-runs replace a file's chunks instead of duplicating them:

```python
vectors = embed(["search_document: " + c for c in chunks])
with conn.cursor() as cur:
    # Re-running replaces a file's chunks instead of duplicating them.
    cur.execute("DELETE FROM chunks WHERE source = %s", (source,))
    cur.executemany(
        "INSERT INTO chunks (source, chunk, embedding) VALUES (%s, %s, %s::vector)",
        [(source, c, to_vector(v)) for c, v in zip(chunks, vectors)],
    )
conn.commit()
```

**`ask.py`** takes a question, embeds it with the `search_query: ` prefix, and asks Postgres for the four closest chunks by cosine distance:

```python
qvec = to_vector(embed("search_query: " + question))
cur.execute(
    "SELECT source, chunk, embedding <=> %s::vector AS distance "
    "FROM chunks ORDER BY distance LIMIT %s",
    (qvec, TOP_K),
)
```

It joins those chunks into a notes section, each labeled with its file name, and sends a prompt to `/api/generate` on `llama3.2:3b` with a low temperature:

```python
prompt = (
    "You answer questions about a home AI lab using only the notes below. "
    "If the notes don't contain the answer, say you don't know.\n\n"
    f"NOTES:\n{context}\n\nQUESTION: {question}\nANSWER:"
)
r = requests.post(f"{OLLAMA}/api/generate",
                  json={"model": CHAT_MODEL, "prompt": prompt, "stream": False,
                        "options": {"temperature": 0.2}},
                  timeout=300)
```

It prints the answer, then each source with its distance and the first 70 characters of the chunk. Lower distance means closer. Showing the sources makes it easy to check whether an answer came from the right place.

One leftover from the first plan: both scripts still default to `127.0.0.1:11435` and `127.0.0.1:15432` when their environment variables are missing. In the pod, `OLLAMA_URL` and `PG_DSN` override those defaults with the cluster DNS names.

## Step 8: Apply the worker and ingest the notes

From my terminal:

```text
$ kubectl apply -f ~/ssi-platform/k8s/day-04-rag-worker.yaml
persistentvolume/rag-docs-pv unchanged
persistentvolumeclaim/rag-docs unchanged
configmap/rag-scripts unchanged
deployment.apps/rag-worker unchanged
$ kubectl -n si-lab get pods -w
NAME                          READY   STATUS    RESTARTS   AGE
ollama-768d64b4c8-wqpq6       1/1     Running   0          14h
pgvector-0                    1/1     Running   0          69m
rag-worker-5fd846c57b-hhc98   1/1     Running   0          45m
```

This output is from a re-apply, which is why every object says `unchanged`. All three pods are running side by side in `si-lab`: the model server, the database, and the worker.

Then the ingest, run inside the worker pod:

```text
$ kubectl -n si-lab exec deploy/rag-worker -- python ingest.py
day-01-host-hardening.md: 6 chunks stored
day-02-secure-k3s.md: 12 chunks stored
day-03-model-serving.md: 14 chunks stored
```

That's 32 chunks in total. To confirm they were really in the database, I counted them from the Postgres pod:

```text
$ kubectl -n si-lab exec pgvector-0 -- psql -U rag -d rag -c "select source, count(*) from chunks group by source;"
          source          | count 
--------------------------+-------
 day-01-host-hardening.md |     6
 day-03-model-serving.md  |    14
 day-02-secure-k3s.md     |    12
(3 rows)
```

The counts match what the ingest printed.

## Step 9: Ask my notes some questions

I asked three questions I already knew the answers to, so I could judge the results. From my terminal:

```text
$ kubectl -n si-lab exec deploy/rag-worker -- python ask.py "Why did I use a static PersistentVolume for the Ollama models?"
You used a static PersistentVolume for the Ollama models because the `hostPath` volume was rejected by the baseline Pod Security level, which enforces a specific security policy. By using a static PersistentVolume, you were able to bind a PersistentVolumeClaim to it, which allowed the pod to access the model files on the external drive while keeping the security policy intact.

Sources:
  0.235  day-03-model-serving.md  ```yaml apiVersion: v1 kind: PersistentVolume metadata: name: ollama-m...
  0.255  day-03-model-serving.md  - Ollama running as a Deployment in `si-lab` under the baseline Pod Se...
  0.275  day-03-model-serving.md  **A small model that fits the GPU.** The card has 4 GB of video memory...
  0.284  day-02-secure-k3s.md  One real constraint shapes what comes next. This GPU has 4 GB of memor...
```

````text
$ kubectl -n si-lab exec deploy/rag-worker -- python ask.py "How do I reach the k3s API from my terminal?"
To reach the k3s API from your terminal, you need to open an SSH tunnel, as described in the notes. 

In a terminal on the workstation, in its own tab:

```bash
ssh -N -L 6443:127.0.0.1:6443 labuser@<lab-lan-ip>
```

This sets up a tunnel that forwards port 6443 on your workstation to port 6443 on the lab host's loopback interface.

Sources:
  0.289  day-01-host-hardening.md  ## Next: day 2 (`day-02-secure-k3s`) 1. Optional: fix broken apt sourc...
  0.296  day-02-secure-k3s.md  **Single-node k3s.** k3s is a lightweight, fully conformant Kubernetes...
  0.305  day-02-secure-k3s.md  ```bash sudo k3s kubectl create namespace si-lab sudo k3s kubectl crea...
  0.315  day-02-secure-k3s.md  **Cluster data on the internal SSD, models on the external drive.** Th...
````

```text
$ kubectl -n si-lab exec deploy/rag-worker -- python ask.py "What GPU is in the lab host and how much VRAM does it have?"
The lab host has an NVIDIA laptop GPU, and it has 4 GB of video memory.

Sources:
  0.260  day-03-model-serving.md  `PROCESSOR` is the column that matters, and `100% GPU` is the proof. A...
  0.261  day-02-secure-k3s.md  One real constraint shapes what comes next. This GPU has 4 GB of memor...
  0.281  day-02-secure-k3s.md  # Day 2: A secure single-node k3s cluster with a working GPU Yesterday...
  0.289  day-03-model-serving.md  # Day 3 — Serving a local LLM on the GPU inside k3s Yesterday I finish...
```

## What I noticed

- **All three answers were correct and grounded in the notes.** The static PersistentVolume answer follows the reasoning in my day 3 note: the baseline level rejects an inline `hostPath`, but a pod may use a claim bound to a static volume. The GPU answer matched my notes exactly.
- **The right documents came up each time.** Distances ranged from 0.235 to 0.315, and the top sources were the relevant files for each question.
- **The best chunk didn't always rank first.** For the k3s API question, the top hits were related chunks from day 1 and day 2, and the chunk that actually holds the tunnel command came in third, at 0.305. Its preview starts with the namespace commands from day 2's Step 2, because that 1200-character chunk also swept in the start of Step 3. The model still produced the right command, but this tells me my chunks mix topics. Smaller chunks, or chunks with some overlap, are the next thing to tune.
- **The model repeats the source wording.** The answer said "workstation", which is what my day 2 note called my terminal, and it reproduced the redacted `labuser@<lab-lan-ip>` word for word. RAG reflects the text it retrieves, so how carefully I write and redact my notes directly shapes the answers.
- **Where everything runs.** The notes sit on the external drive. Embeddings and generation happen on the GPU through Ollama. Vectors live in Postgres on the internal NVMe drive. The scripts run in a pod. My terminal only sent `kubectl` commands.

## Where the lab stands

- Ollama in `si-lab` serving both `llama3.2:3b` and `nomic-embed-text` on the GPU
- Postgres 17 with pgvector 0.8.6 as the StatefulSet `pgvector`, behind a ClusterIP Service on port 5432, with its data on the internal NVMe drive through the claim `data-pgvector-0`
- The database password in the Secret `pgvector-auth`, referenced by name and never written into a manifest
- A `chunks` table with an HNSW cosine index, holding 32 chunks from my day 1 to day 3 notes
- The `rag-worker` pod with `ingest.py` and `ask.py` mounted from a ConfigMap and my notes mounted read-only from the external drive
- Everything under the baseline Pod Security level, with nothing new exposed on my home network

It's small, but it's the same shape as a production RAG service: documents on storage, an embedding model and a chat model behind an internal endpoint, a vector index in a real database, and the glue running as a workload in the cluster.

## Next: Day 5

A few things I want to clean up first:

- Run ingestion as a Kubernetes Job instead of through `kubectl exec`.
- Build a custom image with the Python libraries baked in, instead of running `pip install` every time the pod starts. That also removes the need to reach PyPI at runtime.
- Try smaller chunks and chunk overlap, then ask the same three questions again and compare the sources.
- Put the Kubernetes manifests in Git.

The main idea for day 5 is an MCP server that exposes this retrieval as a tool, so agents can search my notes. After that comes SQL and lab data in the style of Dynamics 365 Finance & Operations, and eventually promoting the whole setup to AKS.

## How this maps to Azure (AKS)

- **The vector store.** Azure Database for PostgreSQL Flexible Server supports the pgvector extension, so the same table, index, and `<=>` queries carry over without a StatefulSet to manage.
- **Embeddings and generation.** Ollama can move to an AKS GPU node pool as described on day 3. Alternatively, Azure OpenAI can provide the embeddings and the chat model, with the worker calling it instead of the in-cluster Service.
- **The documents.** Azure Files or Azure Blob Storage replaces the external drive, mounted through their CSI drivers or read directly by the ingest job.
- **The secret.** Azure Key Vault with the Secrets Store CSI driver replaces the `kubectl create secret` step, so the password never has to be typed into a terminal.
- **Identity.** With workload identity, the worker pod gets its own Microsoft Entra identity for Key Vault, storage, and Azure OpenAI, instead of relying on shared keys.

## AWS delta

On AWS, the matching pieces are RDS or Aurora PostgreSQL with the pgvector extension, EKS GPU nodes for Ollama or Amazon Bedrock for embeddings, S3 for the documents, and AWS Secrets Manager for the database password.
