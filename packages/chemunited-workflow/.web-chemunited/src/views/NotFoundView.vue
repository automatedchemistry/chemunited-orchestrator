<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div>
        <p class="page-eyebrow">Not found</p>
        <h1 class="page-title">No page at {{ route.path }}</h1>
        <p class="page-description">
          It may be a project page that is not declared in
          <code>customizations/ui/ui_hook.py</code>, or a mistyped address.
          <RouterLink to="/">Back to the Dashboard</RouterLink>.
        </p>
      </div>
    </header>
  </div>
</template>
