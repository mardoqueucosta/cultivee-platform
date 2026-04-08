/*
  Cultivee - Configuracao de Build

  1. Escolha o PRODUTO (descomente a linha correspondente)
  2. Escolha o AMBIENTE (ENV_LOCAL ou ENV_PRODUCTION)
*/

// ===== AMBIENTE ATIVO =====
// #define ENV_LOCAL
#define ENV_PRODUCTION
// ==========================

// ===== PRODUTO ATIVO (descomente apenas um) =====
#include "../products/hidro.h"
// #include "../products/cam.h"
// =================================================

// Protecao contra configuracao errada
#if !defined(ENV_LOCAL) && !defined(ENV_PRODUCTION)
  #error "Defina ENV_LOCAL ou ENV_PRODUCTION em config.h"
#endif
#if defined(ENV_LOCAL) && defined(ENV_PRODUCTION)
  #error "Defina APENAS um: ENV_LOCAL ou ENV_PRODUCTION em config.h"
#endif
