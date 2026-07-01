<script setup lang="ts">
// 应用根：只承载路由出口。/login → AuthView（独立登录页），其余 → LiveView（主应用）。
// 说明：演示态的 TopBar/Sidebar 等组件仍在仓库、未挂载。
</script>

<template>
  <router-view />
</template>
