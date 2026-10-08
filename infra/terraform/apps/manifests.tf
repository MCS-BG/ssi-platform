# Raw manifests: the repo's own k8s/*.yaml and models/*.yaml are the single
# source of truth. Each file is split on "---" and every object is picked by
# kind/name below, so a later Day file can supersede an earlier one (for
# example day-08b-mcp-server.yaml replaces the Day 6 mcp-server Deployment)
# without editing the earlier file. Nothing is rewritten in HCL except the few
# opt-in patches in locals.patched (AKS scheduling/storage/CIDRs, gateway Service type).

locals {
  repo_root = coalesce(var.repo_root, abspath("${path.module}/../../.."))

  manifest_files = toset([
    "k8s/day-13-namespaces.yaml",
    "k8s/day-03/ollama.yaml",
    "k8s/day-04-pgvector.yaml",
    "k8s/day-04-rag-worker.yaml",
    "k8s/day-05-open-webui.yaml",
    "k8s/day-05-open-webui-theme.yaml",
    "k8s/day-06-mcp.yaml",
    "k8s/day-06-netpol-pgvector.yaml",
    "k8s/day-07-namespaces.yaml",
    "k8s/day-07-netpol.yaml",
    "k8s/day-07-prompt-guard.yaml",
    "k8s/day-08a-mcp-test.yaml",
    "k8s/day-08a-prompt-guard.yaml",
    "k8s/day-08a-rag-worker.yaml",
    "k8s/day-08b-mcp-server.yaml",
    "k8s/day-08b-tailscale-ingress.yaml",
    "k8s/day-08b-tailscale-namespace.yaml",
    "k8s/day-10-control-layer.yaml",
    "k8s/day-10-engineering-mcp.yaml",
    "k8s/day-11-ssi-gateway.yaml",
    "k8s/day-14-m365-mcp.yaml",
    "k8s/day-15-control-layer-memory.yaml",
    "k8s/day-16-control-layer.yaml",
    "k8s/day-16-engineering-mcp-github.yaml",
    "models/day-05b-ollama-models.yaml",
  ])

  # Every YAML document in those files, keyed "file|Kind|name".
  raw_docs = merge([
    for f in local.manifest_files : {
      for doc in split("\n---\n", "\n${file("${local.repo_root}/${f}")}\n") :
      "${f}|${yamldecode(doc).kind}|${yamldecode(doc).metadata.name}" => "${trimspace(doc)}\n"
      if trimspace(replace(doc, "/(?m)^\\s*#.*$/", "")) != ""
    }
  ]...)

  helm_ssi    = var.ssi_control_plane_mode == "helm"
  use_ollama  = var.enable_ollama && var.model_backend == "ollama"
  use_vllm    = var.model_backend == "vllm"
  observ      = var.enable_observability
  lf          = var.enable_langfuse
  ts          = var.enable_tailscale_ingress
  app_objects = !local.helm_ssi
  # Day 16 control layer (model planner + Day 15 memory) supersedes the Day 15 and Day 10
  # control-layer ConfigMap + Deployment. Memory off = MEMORY_ENABLED=false patched in below.
  memory  = var.enable_conversation_memory && var.enable_pgvector
  cl_file = "k8s/day-16-control-layer.yaml"
  eng_src = var.enable_engineering_mcp_github ? "k8s/day-16-engineering-mcp-github.yaml" : "k8s/day-10-engineering-mcp.yaml"

  # Which object comes from which file, and whether it is enabled.
  # key = "<namespace or _cluster>/<Kind>/<name>" (stable resource address).
  catalog = {
    # Namespaces
    "_cluster/Namespace/si-lab"              = { src = "k8s/day-13-namespaces.yaml", on = true }
    "_cluster/Namespace/gpu-system"          = { src = "k8s/day-13-namespaces.yaml", on = var.enable_nvidia_device_plugin }
    "_cluster/Namespace/monitoring"          = { src = "k8s/day-07-namespaces.yaml", on = local.observ || local.lf }
    "_cluster/Namespace/monitoring-host"     = { src = "k8s/day-07-namespaces.yaml", on = local.observ }
    "_cluster/Namespace/langfuse"            = { src = "k8s/day-07-namespaces.yaml", on = local.lf }
    "_cluster/Namespace/cert-manager"        = { src = "k8s/day-07-namespaces.yaml", on = local.lf }
    "_cluster/Namespace/clickhouse-operator" = { src = "k8s/day-07-namespaces.yaml", on = local.lf }
    "_cluster/Namespace/tailscale"           = { src = "k8s/day-08b-tailscale-namespace.yaml", on = local.ts }

    # Ollama (model slot) + pinned model list
    "_cluster/PersistentVolume/ollama-models-pv" = { src = "k8s/day-03/ollama.yaml", on = local.use_ollama && var.use_host_path_volumes }
    "si-lab/PersistentVolumeClaim/ollama-models" = { src = "k8s/day-03/ollama.yaml", on = local.use_ollama }
    "si-lab/Deployment/ollama"                   = { src = "k8s/day-03/ollama.yaml", on = local.use_ollama }
    "si-lab/Service/ollama"                      = { src = "k8s/day-03/ollama.yaml", on = local.use_ollama }
    "si-lab/ConfigMap/ollama-models"             = { src = "models/day-05b-ollama-models.yaml", on = local.use_ollama }
    "si-lab/ConfigMap/ollama-pull-script"        = { src = "models/day-05b-ollama-models.yaml", on = local.use_ollama }
    "si-lab/Job/ollama-pull"                     = { src = "models/day-05b-ollama-models.yaml", on = local.use_ollama && var.enable_model_pull_job }

    # pgvector
    "si-lab/Service/pgvector"                     = { src = "k8s/day-04-pgvector.yaml", on = var.enable_pgvector }
    "si-lab/StatefulSet/pgvector"                 = { src = "k8s/day-04-pgvector.yaml", on = var.enable_pgvector }
    "si-lab/NetworkPolicy/pgvector-allow-clients" = { src = "k8s/day-06-netpol-pgvector.yaml", on = var.enable_pgvector && var.enable_pgvector_netpol }

    # RAG worker (Day 8a image build supersedes the Day 4 ConfigMap version)
    "_cluster/PersistentVolume/rag-docs-pv" = { src = "k8s/day-04-rag-worker.yaml", on = var.enable_rag_worker && var.use_host_path_volumes }
    "si-lab/PersistentVolumeClaim/rag-docs" = { src = "k8s/day-04-rag-worker.yaml", on = var.enable_rag_worker }
    "si-lab/Deployment/rag-worker"          = { src = "k8s/day-08a-rag-worker.yaml", on = var.enable_rag_worker }

    # Open WebUI (theme file supersedes the plain Deployment)
    "si-lab/PersistentVolumeClaim/open-webui-data" = { src = "k8s/day-05-open-webui.yaml", on = var.enable_open_webui }
    "si-lab/Service/open-webui"                    = { src = "k8s/day-05-open-webui.yaml", on = var.enable_open_webui }
    "si-lab/ConfigMap/open-webui-theme"            = { src = "k8s/day-05-open-webui-theme.yaml", on = var.enable_open_webui }
    "si-lab/Deployment/open-webui"                 = { src = "k8s/day-05-open-webui-theme.yaml", on = var.enable_open_webui }

    # Prompt Guard (Day 8a image build supersedes the Day 7 Deployment)
    "si-lab/PersistentVolumeClaim/prompt-guard-cache" = { src = "k8s/day-07-prompt-guard.yaml", on = var.enable_prompt_guard }
    "si-lab/Service/prompt-guard"                     = { src = "k8s/day-07-prompt-guard.yaml", on = var.enable_prompt_guard }
    "si-lab/NetworkPolicy/prompt-guard-allow-si-lab"  = { src = "k8s/day-07-prompt-guard.yaml", on = var.enable_prompt_guard }
    "si-lab/Deployment/prompt-guard"                  = { src = "k8s/day-08a-prompt-guard.yaml", on = var.enable_prompt_guard }

    # Business MCP slot: mcp-server (fo_* tools) + fo-mock
    "si-lab/ConfigMap/fo-mock-code"                 = { src = "k8s/day-06-mcp.yaml", on = var.enable_business_mcp }
    "si-lab/Deployment/fo-mock"                     = { src = "k8s/day-06-mcp.yaml", on = var.enable_business_mcp }
    "si-lab/Service/fo-mock"                        = { src = "k8s/day-06-mcp.yaml", on = var.enable_business_mcp }
    "si-lab/NetworkPolicy/fo-mock-allow-mcp-server" = { src = "k8s/day-06-mcp.yaml", on = var.enable_business_mcp }
    "si-lab/NetworkPolicy/mcp-server-allow-si-lab"  = { src = "k8s/day-06-mcp.yaml", on = var.enable_business_mcp }
    "si-lab/Service/mcp-server"                     = { src = "k8s/day-06-mcp.yaml", on = var.enable_business_mcp && local.app_objects }
    "si-lab/Deployment/mcp-server"                  = { src = "k8s/day-08b-mcp-server.yaml", on = var.enable_business_mcp && local.app_objects }
    "si-lab/ConfigMap/mcp-test-code"                = { src = "k8s/day-08a-mcp-test.yaml", on = var.enable_business_mcp }
    "si-lab/Job/mcp-test"                           = { src = "k8s/day-08a-mcp-test.yaml", on = var.enable_business_mcp && var.enable_smoke_test_job }

    # Day 10 control layer + engineering MCP slot
    "si-lab/ConfigMap/control-layer-code"               = { src = local.cl_file, on = var.enable_control_layer && local.app_objects }
    "si-lab/Deployment/control-layer"                   = { src = local.cl_file, on = var.enable_control_layer && local.app_objects }
    "si-lab/Service/control-layer"                      = { src = "k8s/day-10-control-layer.yaml", on = var.enable_control_layer && local.app_objects }
    "si-lab/NetworkPolicy/control-layer-allow-si-lab"   = { src = "k8s/day-10-control-layer.yaml", on = var.enable_control_layer }
    "si-lab/ConfigMap/engineering-mcp-code"             = { src = local.eng_src, on = var.enable_engineering_mcp && local.app_objects }
    "si-lab/Deployment/engineering-mcp"                 = { src = local.eng_src, on = var.enable_engineering_mcp && local.app_objects }
    "si-lab/Service/engineering-mcp"                    = { src = "k8s/day-10-engineering-mcp.yaml", on = var.enable_engineering_mcp && local.app_objects }
    "si-lab/NetworkPolicy/engineering-mcp-allow-si-lab" = { src = "k8s/day-10-engineering-mcp.yaml", on = var.enable_engineering_mcp }

    # Day 16: real GitHub data for the engineering slot (supersedes the Day 10 code + Deployment).
    "si-lab/NetworkPolicy/engineering-mcp-egress" = { src = "k8s/day-16-engineering-mcp-github.yaml", on = var.enable_engineering_mcp && var.enable_engineering_mcp_github }

    # Day 14 productivity MCP slot (Microsoft 365). Secret m365-mcp-auth is created by hand after sign-in.
    "si-lab/ConfigMap/m365-mcp-code"                    = { src = "k8s/day-14-m365-mcp.yaml", on = var.enable_m365_mcp && local.app_objects }
    "si-lab/Deployment/m365-mcp"                        = { src = "k8s/day-14-m365-mcp.yaml", on = var.enable_m365_mcp && local.app_objects }
    "si-lab/Service/m365-mcp"                           = { src = "k8s/day-14-m365-mcp.yaml", on = var.enable_m365_mcp && local.app_objects }
    "si-lab/NetworkPolicy/m365-mcp-allow-control-layer" = { src = "k8s/day-14-m365-mcp.yaml", on = var.enable_m365_mcp }

    # Day 15 conversation memory: the control layer may reach pgvector on 5432 (both modes).
    # Only next to the Day 6 policy: on its own it would shut mcp-server and rag-worker out of pgvector.
    "si-lab/NetworkPolicy/pgvector-allow-control-layer" = { src = "k8s/day-16-control-layer.yaml", on = var.enable_control_layer && local.memory && var.enable_pgvector_netpol }

    # Day 11 ssi-gateway
    "si-lab/ConfigMap/ssi-gateway-code"      = { src = "k8s/day-11-ssi-gateway.yaml", on = var.enable_ssi_gateway && local.app_objects }
    "si-lab/Deployment/ssi-gateway"          = { src = "k8s/day-11-ssi-gateway.yaml", on = var.enable_ssi_gateway && local.app_objects }
    "si-lab/Service/ssi-gateway"             = { src = "k8s/day-11-ssi-gateway.yaml", on = var.enable_ssi_gateway && local.app_objects }
    "si-lab/NetworkPolicy/ssi-gateway-allow" = { src = "k8s/day-11-ssi-gateway.yaml", on = var.enable_ssi_gateway }
    "si-lab/Ingress/ssi-gateway"             = { src = "k8s/day-11-ssi-gateway.yaml", on = var.enable_ssi_gateway && local.ts }

    # Observability NetworkPolicies (Day 7)
    "monitoring/NetworkPolicy/otel-collector-ingress" = { src = "k8s/day-07-netpol.yaml", on = local.observ }
    "monitoring/NetworkPolicy/loki-ingress"           = { src = "k8s/day-07-netpol.yaml", on = local.observ }
    "monitoring/NetworkPolicy/tempo-ingress"          = { src = "k8s/day-07-netpol.yaml", on = local.observ }
    "langfuse/NetworkPolicy/langfuse-same-namespace"  = { src = "k8s/day-07-netpol.yaml", on = local.lf }
    "langfuse/NetworkPolicy/langfuse-web-ingress"     = { src = "k8s/day-07-netpol.yaml", on = local.lf }

    # Home-lab only: Tailscale Ingresses (Day 8b)
    "si-lab/Ingress/open-webui"                          = { src = "k8s/day-08b-tailscale-ingress.yaml", on = local.ts && var.enable_open_webui }
    "monitoring/Ingress/grafana"                         = { src = "k8s/day-08b-tailscale-ingress.yaml", on = local.ts && local.observ }
    "langfuse/Ingress/langfuse"                          = { src = "k8s/day-08b-tailscale-ingress.yaml", on = local.ts && local.lf }
    "langfuse/NetworkPolicy/langfuse-web-from-tailscale" = { src = "k8s/day-08b-tailscale-ingress.yaml", on = local.ts && local.lf }
  }

  selected_raw = {
    for k, v in local.catalog : k => local.raw_docs["${v.src}|${split("/", k)[1]}|${split("/", k)[2]}"]
    if v.on
  }

  # ---- image registry + opt-in pinning ("ref in k8s/*.yaml" => "ref to deploy") ----
  workload_kinds  = ["Deployment", "StatefulSet", "Job"]
  repo_image_base = "ghcr.io/mcs-bg/"
  all_images = distinct(flatten([
    for k, d in local.selected_raw : [
      for c in concat(yamldecode(d).spec.template.spec.containers, try(yamldecode(d).spec.template.spec.initContainers, [])) : c.image
    ] if contains(local.workload_kinds, split("/", k)[1])
  ]))
  registry_overrides = trimsuffix(var.image_registry, "/") == trimsuffix(local.repo_image_base, "/") ? {} : {
    for img in local.all_images : img => "${trimsuffix(var.image_registry, "/")}/${trimprefix(img, local.repo_image_base)}"
    if startswith(img, local.repo_image_base)
  }
  image_map = merge(local.registry_overrides, var.image_overrides)
  image_patch_keys = toset([
    for k, d in local.selected_raw : k
    if contains(local.workload_kinds, split("/", k)[1]) && anytrue([
      for c in concat(yamldecode(d).spec.template.spec.containers, try(yamldecode(d).spec.template.spec.initContainers, [])) :
      contains(keys(local.image_map), c.image)
    ])
  ])
  image_patched = {
    for k in local.image_patch_keys : k => yamlencode(merge(yamldecode(local.selected_raw[k]), {
      spec = merge(yamldecode(local.selected_raw[k]).spec, {
        template = merge(yamldecode(local.selected_raw[k]).spec.template, {
          spec = merge(
            yamldecode(local.selected_raw[k]).spec.template.spec,
            { containers = [for c in yamldecode(local.selected_raw[k]).spec.template.spec.containers : merge(c, { image = lookup(local.image_map, c.image, c.image) })] },
            { for ik, iv in { initContainers = [for c in try(yamldecode(local.selected_raw[k]).spec.template.spec.initContainers, []) : merge(c, { image = lookup(local.image_map, c.image, c.image) })] } : ik => iv if length(iv) > 0 },
          )
        })
      })
    }))
  }
  selected = merge(local.selected_raw, local.image_patched)

  # ---- opt-in patches (no-ops with lab defaults, so the lab text is untouched) ----

  ollama_doc = yamldecode(lookup(local.selected, "si-lab/Deployment/ollama", local.raw_docs["k8s/day-03/ollama.yaml|Deployment|ollama"]))
  ollama_patch_needed = (
    !var.ollama_gpu ||
    var.ollama_runtime_class_name != "nvidia" ||
    length(var.ollama_node_selector) > 0 ||
    length(var.ollama_tolerations) > 0
  )
  ollama_pod_spec = merge(
    { for k, v in local.ollama_doc.spec.template.spec : k => v if !contains(["runtimeClassName", "containers"], k) },
    {
      containers = [for c in local.ollama_doc.spec.template.spec.containers : merge(c, {
        resources = merge(c.resources, {
          limits = { for rk, rv in c.resources.limits : rk => rv if var.ollama_gpu || rk != "nvidia.com/gpu" }
        })
      })]
    },
    { for k, v in { runtimeClassName = var.ollama_runtime_class_name } : k => v if v != "" && var.ollama_gpu },
    { for k, v in { nodeSelector = var.ollama_node_selector } : k => v if length(v) > 0 },
    { for k, v in { tolerations = var.ollama_tolerations } : k => v if length(v) > 0 },
  )
  ollama_patched = yamlencode(merge(local.ollama_doc, {
    spec = merge(local.ollama_doc.spec, {
      template = merge(local.ollama_doc.spec.template, { spec = local.ollama_pod_spec })
    })
  }))

  # Dynamic PVCs instead of the lab's static hostPath PVs.
  pvc_sizes = {
    "si-lab/PersistentVolumeClaim/ollama-models" = var.ollama_models_volume_size
    "si-lab/PersistentVolumeClaim/rag-docs"      = null
  }
  pvc_patched = {
    for k, size in local.pvc_sizes : k => yamlencode(merge(yamldecode(local.selected[k]), {
      spec = merge(
        { for sk, sv in yamldecode(local.selected[k]).spec : sk => sv if !contains(["storageClassName", "volumeName", "resources"], sk) },
        { for sk, sv in { storageClassName = var.storage_class_name } : sk => sv if sv != null },
        { resources = { requests = { storage = coalesce(size, yamldecode(local.selected[k]).spec.resources.requests.storage) } } },
      )
    }))
    if !var.use_host_path_volumes && contains(keys(local.selected), k)
  }

  # ssi-gateway Service + NetworkPolicy. The YAML is the lab (NodePort 30808,
  # externalTrafficPolicy Local, LAN ipBlock). Patched only when the env differs, so
  # lab-k3s keeps the manifest text and cloud envs get a ClusterIP Service (plus the
  # internal LB in ssi_chart.tf) with only gateway_allowed_cidrs as ipBlocks.
  gw_svc_key   = "si-lab/Service/ssi-gateway"
  gw_svc_doc   = try(yamldecode(local.selected[local.gw_svc_key]), null)
  gw_node_port = var.gateway_service_type == "NodePort"
  gw_svc_spec = local.gw_svc_doc == null ? null : merge(
    { for k, v in local.gw_svc_doc.spec : k => v if !contains(["type", "externalTrafficPolicy", "ports"], k) },
    { type = var.gateway_service_type },
    { for k, v in { externalTrafficPolicy = "Local" } : k => v if local.gw_node_port },
    {
      ports = [for p in local.gw_svc_doc.spec.ports : merge(
        { for pk, pv in p : pk => pv if pk != "nodePort" },
        { for pk, pv in { nodePort = var.gateway_node_port } : pk => pv if local.gw_node_port },
      )]
    },
  )
  gw_svc_patched = local.gw_svc_doc == null || jsonencode(local.gw_svc_spec) == jsonencode(try(local.gw_svc_doc.spec, null)) ? {} : {
    (local.gw_svc_key) = yamlencode(merge(local.gw_svc_doc, { spec = local.gw_svc_spec }))
  }

  gw_np_key = "si-lab/NetworkPolicy/ssi-gateway-allow"
  gw_np_doc = try(yamldecode(local.selected[local.gw_np_key]), null)
  gw_np_from = concat(
    [for f in try(local.gw_np_doc.spec.ingress[0].from, []) : f if !can(f.ipBlock)],
    [for c in compact([var.gateway_lan_cidr]) : { ipBlock = { cidr = c } }],
    [for c in var.gateway_allowed_cidrs : { ipBlock = { cidr = c } }],
  )
  gw_np_patched = local.gw_np_doc == null || jsonencode(local.gw_np_from) == jsonencode(try(local.gw_np_doc.spec.ingress[0].from, null)) ? {} : {
    (local.gw_np_key) = yamlencode(merge(local.gw_np_doc, {
      spec = merge(local.gw_np_doc.spec, {
        ingress = concat(
          [merge(local.gw_np_doc.spec.ingress[0], { from = local.gw_np_from })],
          slice(local.gw_np_doc.spec.ingress, 1, length(local.gw_np_doc.spec.ingress)),
        )
      })
    }))
  }

  # Control-layer env overrides. Only patched when something differs from the lab
  # defaults in k8s/day-16-control-layer.yaml (Ollama, PLANNER=model, memory on,
  # ENGINEERING_DEFAULT_REPO=ssi-platform), so the lab's manifest text stays untouched.
  # model_backend = vllm switches planning and synthesis to the OpenAI-compatible API.
  vllm_served_name = var.vllm_served_model_name != "" ? var.vllm_served_model_name : var.vllm_model_id
  model_env = merge(
    !local.use_vllm ? {} : {
      LLM_BACKEND     = "openai"
      OPENAI_BASE_URL = "http://vllm.si-lab.svc.cluster.local:8000/v1"
      OPENAI_MODEL    = local.vllm_served_name
      MODEL           = local.vllm_served_name
    },
    local.memory ? {} : { MEMORY_ENABLED = "false" },
    var.control_layer_planner == "model" ? {} : { PLANNER = var.control_layer_planner },
    var.engineering_default_repo == "ssi-platform" ? {} : { ENGINEERING_DEFAULT_REPO = var.engineering_default_repo },
  )
  cl_key = "si-lab/Deployment/control-layer"
  cl_patched = length(local.model_env) == 0 || !contains(keys(local.selected), local.cl_key) ? {} : {
    (local.cl_key) = yamlencode(merge(yamldecode(local.selected[local.cl_key]), {
      spec = merge(yamldecode(local.selected[local.cl_key]).spec, {
        template = merge(yamldecode(local.selected[local.cl_key]).spec.template, {
          spec = merge(yamldecode(local.selected[local.cl_key]).spec.template.spec, {
            containers = [for c in yamldecode(local.selected[local.cl_key]).spec.template.spec.containers : merge(c, {
              env = concat(
                [for e in c.env : e if !contains(keys(local.model_env), e.name)],
                [for k, val in local.model_env : { name = k, value = val }],
              )
            })]
          })
        })
      })
    }))
  }

  # vLLM objects rendered from k8s/day-13-vllm.yaml.tftpl.
  vllm_args = concat(
    [
      "--model", var.vllm_model_id,
      "--served-model-name", local.vllm_served_name,
      "--tensor-parallel-size", tostring(var.vllm_tensor_parallel_size),
      "--max-model-len", tostring(var.vllm_max_model_len),
      "--download-dir", "/models",
      "--port", "8000",
    ],
    var.vllm_quantization == "none" ? [] : ["--quantization", var.vllm_quantization],
    var.vllm_enable_expert_parallel ? ["--enable-expert-parallel"] : [],
    var.vllm_extra_args,
  )
  vllm_rendered = templatefile("${local.repo_root}/k8s/day-13-vllm.yaml.tftpl", {
    image             = var.vllm_image
    args              = jsonencode(local.vllm_args)
    gpu_count         = var.vllm_gpu_count
    cpu_request       = var.vllm_cpu_request
    memory_request    = var.vllm_memory_request
    memory_limit      = var.vllm_memory_limit
    shm_size          = var.vllm_shm_size
    weights_size      = var.vllm_weights_size
    weights_host_path = var.vllm_weights_host_path
    storage_class     = var.storage_class_name == null ? "" : var.storage_class_name
    runtime_class     = var.vllm_runtime_class_name
    node_selector     = jsonencode(var.vllm_node_selector)
    tolerations       = jsonencode(var.vllm_tolerations)
    hf_token_secret   = var.hf_token_secret_name
  })
  vllm_docs = !local.use_vllm ? {} : {
    for doc in split("\n---\n", "\n${local.vllm_rendered}\n") :
    "${try(yamldecode(doc).metadata.namespace, "_cluster")}/${yamldecode(doc).kind}/${yamldecode(doc).metadata.name}" => "${trimspace(doc)}\n"
    if trimspace(replace(doc, "/(?m)^\\s*#.*$/", "")) != ""
  }

  patched = merge(
    local.selected,
    local.cl_patched,
    local.vllm_docs,
    local.use_ollama && local.ollama_patch_needed ? { "si-lab/Deployment/ollama" = local.ollama_patched } : {},
    local.pvc_patched,
    local.gw_svc_patched,
    local.gw_np_patched,
  )

  namespace_docs = { for k, v in local.patched : k => v if startswith(k, "_cluster/Namespace/") }
  object_docs    = { for k, v in local.patched : k => v if !startswith(k, "_cluster/Namespace/") }
}

resource "kubectl_manifest" "namespace" {
  for_each = local.namespace_docs

  yaml_body = each.value

  lifecycle {
    precondition {
      condition     = !(var.azure_openai_endpoint != "" && var.ssi_control_plane_mode == "manifests")
      error_message = "azure_openai_endpoint needs ssi_control_plane_mode = helm."
    }
    precondition {
      condition     = !(var.gateway_service_type == "NodePort" && var.ssi_control_plane_mode == "helm")
      error_message = "gateway_service_type = NodePort is the home-lab manifests path; helm mode uses ClusterIP or gateway_load_balancer."
    }
  }
}

resource "kubectl_manifest" "this" {
  for_each = local.object_docs

  yaml_body        = each.value
  wait_for_rollout = var.wait_for_rollout

  depends_on = [
    kubectl_manifest.namespace,
    kubernetes_secret_v1.app,
  ]
}
