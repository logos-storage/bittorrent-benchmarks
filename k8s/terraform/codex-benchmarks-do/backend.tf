terraform {
  backend "s3" {
    endpoints = {
      s3 = "https://<S3_REGION>.digitaloceanspaces.com"
    }
    bucket = "codex-infra-terraform"
    key    = "clusters/codex-benchmarks-do-<DO_REGION>/terraform.tfstate"
    region = "<S3_REGION>"

    access_key = "<S3_ACCESS_KEY>"
    secret_key = "<S3_SECRET_KEY>"

    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_s3_checksum            = true
  }
}
