# Kubernetes cluster
module "doks" {
  source = "../modules/doks"

  name                            = "codex-benchmarks"
  region                          = var.region
  vpc_ip_range                    = "10.1.0.0/20"
  kubernetes_version              = "1.33.1-do.5"
  kubernetes_ha                   = true
  kubernetes_auto_upgrade         = false
  kubernetes_node_pool_name       = "infra-s-4vcpu-16gb-amd"
  kubernetes_node_pool_size       = "s-4vcpu-16gb-amd"
  kubernetes_node_pool_auto_scale = true
  kubernetes_node_pool_min        = 1
  kubernetes_node_pool_max        = 4
  kubernetes_node_pool_tags       = ["default", "autoscale"]
  kubernetes_node_pool_labels = {
    default-pool  = "true"
    scaling-type  = "auto"
    workload-type = "infra"
  }
}

# Node pool - Codex
resource "digitalocean_kubernetes_node_pool" "codex-d-4vcpu-8gb" {
  cluster_id = module.doks.kubernetes_cluster_id
  name       = "codex-d-4vcpu-8gb"
  size       = "c-4"
  auto_scale = true
  min_nodes  = 1
  max_nodes  = 95
  node_count = 4
  tags       = ["codex"]

  labels = {
    default-pool     = "false"
    scaling-type     = "auto"
    workload-type    = "benchmarks"
  }
}
