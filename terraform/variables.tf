variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "service_name" {
  type    = string
  default = "net-worth-game"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "app_port" {
  type    = number
  default = 8001
}

variable "cpu" {
  type    = string
  default = "1024"
}

variable "memory" {
  type    = string
  default = "2048"
}

variable "db_name" {
  type    = string
  default = "networth"
}

variable "db_username" {
  type    = string
  default = "networth"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}
