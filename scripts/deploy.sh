#!/bin/bash

# 设置错误时退出
set -e

# 显示执行的命令
set -x

# 检查环境变量
if [ -z "$DOCKER_USERNAME" ] || [ -z "$DOCKER_PASSWORD" ]; then
    echo "Error: DOCKER_USERNAME or DOCKER_PASSWORD not set"
    exit 1
fi

# 登录Docker Hub
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin

# 构建镜像
docker-compose build

# 运行测试
docker-compose run web pytest

# 如果测试通过，推送镜像
if [ $? -eq 0 ]; then
    docker-compose push
    
    # 部署到生产环境
    if [ "$DEPLOY_ENV" = "production" ]; then
        # 备份数据库
        docker-compose exec postgres pg_dump -U re_centris re_centris > backup.sql
        
        # 停止旧容器
        docker-compose down
        
        # 启动新容器
        docker-compose up -d
        
        # 等待服务启动
        sleep 30
        
        # 检查服务健康状态
        docker-compose ps | grep "Up" || {
            echo "Error: Service failed to start"
            docker-compose logs
            exit 1
        }
        
        # 运行数据库迁移
        docker-compose exec web python manage.py db upgrade
        
        echo "Deployment successful!"
    else
        echo "Skipping production deployment"
    fi
else
    echo "Tests failed, aborting deployment"
    exit 1
fi 