pipeline {
    agent any

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        IMAGE_NAME = 'restaurant-management'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install dependencies') {
            steps {
                sh 'python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt'
            }
        }

        stage('Unit tests') {
            steps {
                sh '. .venv/bin/activate && python -m unittest discover -s tests -v'
            }
        }

        stage('Security scan (code + dependencies)') {
            steps {
                sh '. .venv/bin/activate && bandit -r app -ll'
                sh '. .venv/bin/activate && pip-audit -r requirements.txt'
            }
        }

        stage('Docker build (versioned)') {
            steps {
                script {
                    env.VERSION = readFile('VERSION').trim()
                }
                sh 'docker build -t ${IMAGE_NAME}:${VERSION} -t ${IMAGE_NAME}:build-${BUILD_NUMBER} .'
            }
        }

        stage('Image scan (Trivy)') {
            steps {
                sh '''docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                      aquasec/trivy:0.55.0 image --severity HIGH,CRITICAL --ignore-unfixed \
                      --exit-code 0 ${IMAGE_NAME}:${VERSION}'''
            }
        }

        stage('Smoke test container') {
            steps {
                sh '''docker rm -f rm-smoke >/dev/null 2>&1 || true
                      docker run -d --name rm-smoke ${IMAGE_NAME}:${VERSION}
                      sleep 6
                      docker exec rm-smoke python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"'''
            }
        }
    }

    post {
        always {
            sh 'docker rm -f rm-smoke >/dev/null 2>&1 || true'
        }
        success {
            echo "Build OK - image ${IMAGE_NAME}:${env.VERSION} is ready"
        }
        failure {
            echo 'Build FAILED - check the stage logs above'
        }
    }
}
