# 기획문서

## 1. 시스템 개요

### 목적
온라인 커머스 오픈마켓에서 구매자 주문 생성, 결제 승인, 환불, 판매자 정산을 하나의 일관된 규칙으로 처리한다. 복수 판매자 상품이 한 주문에 포함되는 경우 판매자 단위로 배송을 분리하고, 배송별로 독립 상태 전이를 관리한다.

### 범위

#### 포함 범위
- 주문 생성과 주문금액 계산
- 결제 승인, 결제 취소, 부분 환불
- 판매자 단위 배송 생성과 배송 상태 관리
- 반품, 교환, 취소 처리
- 쿠폰, 적립금 사용과 환불 재분배
- 재고 예약, 예약 만료 해제, 확정 차감, 재고 복원
- 판매자 정산 금액 계산과 보류 처리
- PG 웹훅 수신과 거래 대사

#### 제외 범위
- 상품 상세 정보 등록과 상품 카탈로그 검색
- 회원 가입과 인증 체계
- 물류 창고 입출고 상세 관리
- 세금계산서 발행과 외부 회계 연동
- 고객 상담 티켓 관리

### 사용자 유형
| 사용자 유형 | 역할 |
|---|---|
| 구매자 | 주문 생성, 결제, 취소, 반품, 교환, 구매확정, 본인 주문/환불/적립금/쿠폰 조회 |
| 판매자 | 본인 상품 포함 주문 조회, 배송 생성, 배송 상태 변경, 환불 승인/거부, 정산 조회 |
| 운영자 | 전체 주문/환불/정산/재고/적립금 조회와 조정, 환불 승인/거부/재시도, 정산 보류/해제, 거래 대사 |
| 시스템 | PG 웹훅 수신, 배치 실행, 상태 전이 자동화, 재고 예약/해제, 정산 집계 |

---

## 2. 도메인 개념

금액은 모두 정수 원 단위이고 통화는 KRW로 고정한다. 시각은 UTC ISO 8601로 다루고,
기간 계산은 KST 기준일을 쓴다.

### 2.1 용어

- **주문**: 구매자가 한 번에 결제하려고 담은 거래 단위. 여러 판매자의 상품이 한 주문에 섞일 수 있다.
- **주문상품**: 주문에 담긴 상품 한 줄. 수량과 단가를 가지며, 취소·반품·교환·배송이 이 단위로 쪼개진다.
- **배송**: 판매자 단위로 묶어서 내보내는 꾸러미. 한 주문에 판매자가 여럿이면 배송도 여럿이 되고, 각 배송은 독립적으로 상태가 움직인다.
- **배송상품**: 어떤 배송에 어떤 주문상품이 몇 개 실렸는지. 한 주문상품이 나뉘어 여러 번 배송될 수 있다.
- **결제**: 한 주문에 대한 결제 기록. 주문 하나에 결제 하나다.
- **결제수단내역**: 그 결제를 무엇으로 얼마씩 냈는지(카드·계좌이체·쿠폰·적립금 등). 한 결제가 여러 수단으로 나뉜다.
- **환불**: 취소·반품으로 돈을 돌려주는 건. 한 주문·한 결제에 환불이 여러 번 생길 수 있다.
- **환불상품**: 그 환불에 어떤 주문상품이 몇 개 포함됐는지.
- **쿠폰**: 구매자가 주문에 한 장 적용할 수 있는 할인. 환불되면 조건에 따라 되살아난다.
- **적립금거래**: 적립금이 늘거나 주는 기록. 주문·환불에 딸려 생기고, 적립금으로 결제한 경우 결제수단내역과 짝이 된다.
- **재고**: 판매 가능 수량을 들고 있는 단위. 여러 주문상품이 같은 재고를 참조한다.
- **정산**: 판매자에게 줄 돈을 기간별로 집계한 것. 미해결 반품·환불이 있으면 일부를 보류한다.

### 2.2 관계

- 주문 하나에 주문상품 여럿, 배송 여럿, 결제 하나, 환불 여럿, 적립금거래 여럿이 딸린다.
- 배송 하나에 배송상품 여럿, 환불 하나에 환불상품 여럿이 딸린다.
- 주문상품 하나가 여러 배송상품·여러 환불상품에 나뉘어 들어갈 수 있다.
- 결제 하나에 결제수단내역 여럿, 환불 여럿이 딸린다.
- 주문상품은 재고 하나를 참조하고, 주문은 쿠폰을 최대 한 장 참조한다.

---

## 3. 상태 전이

### 3.1 주문 대표 상태 산출 규칙 RS-001
주문 대표 상태는 아래 우선순위대로 계산한다. CANCELED 상태인 배송은 forward 배송 계산에서 제외한다.

1. 모든 OrderItem.status가 CANCELED이면 CANCELED
2. Refund.type=CANCEL이고 Refund.status=PG_PROCESSING인 환불이 하나 이상이면 CANCELING
3. Refund.type=CANCEL이고 Refund.status가 REQUESTED, APPROVED, PROCESSING 중 하나인 환불이 하나 이상이면 CANCEL_REQUESTED
4. Shipment.status가 EXCHANGE_PICKUP, EXCHANGE_RECEIVED, EXCHANGE_SHIPPED 중 하나인 배송이 하나 이상이면 EXCHANGING
5. Shipment.status=EXCHANGE_REQUESTED인 배송이 하나 이상이면 EXCHANGE_REQUESTED
6. Shipment.status가 RETURN_PICKUP, RETURN_RECEIVED 중 하나이거나 Refund.type=RETURN이고 Refund.status=PG_PROCESSING인 환불이 하나 이상이면 RETURNING
7. Shipment.status=RETURN_REQUESTED이거나 Refund.type=RETURN이고 Refund.status가 REQUESTED, APPROVED, PROCESSING 중 하나인 환불이 하나 이상이면 RETURN_REQUESTED
8. 취소되지 않은 모든 OrderItem.status가 PURCHASE_CONFIRMED이면 PURCHASE_CONFIRMED
9. 취소되지 않은 모든 OrderItem.status가 RETURNED이면 RETURNED
10. 취소되지 않은 모든 OrderItem.status가 EXCHANGED이면 EXCHANGED
11. 모든 Shipment.status가 DELIVERED이고 모든 OrderItem.status가 DELIVERED 또는 PURCHASE_CONFIRMED이면 ALL_DELIVERED
12. Shipment.status=DELIVERED가 하나 이상이고 Shipment.status가 CREATED, PACKING, SHIPPED 중 하나인 배송이 하나 이상이면 PARTIAL_DELIVERED
13. 모든 Shipment.status가 SHIPPED 또는 DELIVERED이고 SHIPPED가 하나 이상이면 ALL_SHIPPED
14. Shipment.status가 SHIPPED 또는 DELIVERED인 배송이 하나 이상이고 CREATED 또는 PACKING인 배송이 하나 이상이면 PARTIAL_SHIPPED
15. Payment.status가 APPROVED 또는 COMPLETED이고 모든 Shipment.status가 CREATED 또는 PACKING이면 PREPARING
16. Payment.status가 APPROVED 또는 COMPLETED이면 PAYMENT_COMPLETED
17. 위 조건에 해당하지 않으면 PAYMENT_WAITING

### 3.2 주문 상태 전이표
| 현재상태 | 이벤트 | 다음상태 | 전이조건 | 부수효과 |
|---|---|---|---|---|
| PAYMENT_WAITING | PAYMENT_APPROVED | PAYMENT_COMPLETED | Payment.total_amount = Order.total_payment_amount, Payment.status=APPROVED | Payment.paid_amount 설정, OrderItem.status=PAID |
| PAYMENT_WAITING | PAYMENT_FAILED | PAYMENT_WAITING | Payment.status=FAILED | Payment.failure_reason 저장 |
| PAYMENT_WAITING | UNPAID_TIMEOUT | CANCELED | now > Order.stock_reservation_expires_at, Payment.status=WAITING | 재고 예약 해제, Payment.status=CANCELED |
| PAYMENT_COMPLETED | SHIPMENT_CREATED | PREPARING | Shipment 1건 이상 생성 | OrderItem.status=PREPARING |
| PREPARING | SHIPMENT_SHIPPED | RS-001 계산값 | Shipment.status=SHIPPED 1건 이상 | Shipment.shipped_at 설정 |
| PARTIAL_SHIPPED | SHIPMENT_SHIPPED | RS-001 계산값 | Shipment.status=SHIPPED 추가 | Shipment.shipped_at 설정 |
| PARTIAL_SHIPPED | SHIPMENT_DELIVERED | RS-001 계산값 | Shipment.status=DELIVERED 1건 이상 | Shipment.delivered_at 설정 |
| PARTIAL_DELIVERED | SHIPMENT_DELIVERED | RS-001 계산값 | Shipment.status=DELIVERED 추가 | Shipment.delivered_at 설정 |
| ALL_DELIVERED | PURCHASE_CONFIRMED | PURCHASE_CONFIRMED | 모든 OrderItem.status=PURCHASE_CONFIRMED | 정산 집계 대상 표시 |
| PAYMENT_COMPLETED | CANCEL_REQUESTED | RS-001 계산값 | Refund.type=CANCEL, Refund.status=REQUESTED 생성 | Refund 생성 |
| CANCEL_REQUESTED | CANCEL_APPROVED | RS-001 계산값 | Refund.status=APPROVED | Refund.approved_at 설정 |
| CANCELING | CANCEL_COMPLETED | RS-001 계산값 | Refund.status=COMPLETED | 재고 복원, Payment.refunded_amount 증가 |
| ALL_DELIVERED | RETURN_REQUESTED | RS-001 계산값 | Refund.type=RETURN, Refund.status=REQUESTED 생성 | Refund 생성 |
| RETURN_REQUESTED | RETURN_APPROVED | RS-001 계산값 | Refund.status=APPROVED | Refund.approved_at 설정 |
| RETURNING | RETURN_COMPLETED | RS-001 계산값 | Refund.status=COMPLETED | 재고 증가, Payment.refunded_amount 증가 |
| ALL_DELIVERED | EXCHANGE_REQUESTED | RS-001 계산값 | Shipment.status=EXCHANGE_REQUESTED 변경 | 교환 접수 기록 |
| EXCHANGE_REQUESTED | EXCHANGE_COMPLETED | RS-001 계산값 | Shipment.status=EXCHANGE_COMPLETED | 교환 완료 기록 |

### 3.3 주문 불가능 전이
| 현재상태 | 시도 이벤트 | 결과 |
|---|---|---|
| PAYMENT_WAITING | SHIPMENT_SHIPPED | 거부 |
| CANCELED | PAYMENT_APPROVED | 거부 |
| PURCHASE_CONFIRMED | CANCEL_REQUESTED | 거부 |
| CANCELING | EXCHANGE_REQUESTED | 거부 |
| RETURNED | PURCHASE_CONFIRMED | 거부 |

### 3.4 배송 상태 전이표
| 현재상태 | 이벤트 | 다음상태 | 전이조건 | 부수효과 |
|---|---|---|---|---|
| CREATED | PACK_START | PACKING | 판매자 소유 배송 | 없음 |
| CREATED | SHIP | SHIPPED | courier, tracking_number 필수 | shipped_at 설정 |
| PACKING | SHIP | SHIPPED | courier, tracking_number 필수 | shipped_at 설정 |
| CREATED | CANCEL | CANCELED | 연결 OrderItem.status=CANCELED로 변경 승인 | 재고 예약 해제 |
| PACKING | CANCEL | CANCELED | 연결 OrderItem.status=CANCELED로 변경 승인 | 재고 예약 해제 |
| SHIPPED | DELIVER | DELIVERED | 배송 완료 확인 | delivered_at 설정 |
| DELIVERED | RETURN_REQUEST | RETURN_REQUESTED | delivered_at + 7일 이내 | 환불 REQUESTED 생성 |
| RETURN_REQUESTED | RETURN_PICKUP_START | RETURN_PICKUP | 판매자 또는 시스템 승인 | 없음 |
| RETURN_PICKUP | RETURN_RECEIVE | RETURN_RECEIVED | 반품 입고 확인 | 없음 |
| RETURN_RECEIVED | RETURN_COMPLETE | RETURN_COMPLETED | Refund.status=COMPLETED | 재고 증가 |
| DELIVERED | EXCHANGE_REQUEST | EXCHANGE_REQUESTED | delivered_at + 7일 이내, 교환 대상 단가 동일 | 교환 접수 |
| EXCHANGE_REQUESTED | EXCHANGE_PICKUP_START | EXCHANGE_PICKUP | 판매자 또는 시스템 승인 | 없음 |
| EXCHANGE_PICKUP | EXCHANGE_RECEIVE | EXCHANGE_RECEIVED | 교환 상품 입고 | 없음 |
| EXCHANGE_RECEIVED | EXCHANGE_SHIP | EXCHANGE_SHIPPED | 새 배송 생성, courier, tracking_number 필수 | 새 Shipment 생성 |
| EXCHANGE_SHIPPED | EXCHANGE_DELIVER | EXCHANGE_COMPLETED | 교환 배송 완료 | OrderItem.status=EXCHANGED |

### 3.5 배송 불가능 전이
| 현재상태 | 시도 이벤트 | 결과 |
|---|---|---|
| CREATED | DELIVER | 거부 |
| SHIPPED | PACK_START | 거부 |
| DELIVERED | CANCEL | 거부 |
| RETURN_COMPLETED | RETURN_REQUEST | 거부 |
| EXCHANGE_COMPLETED | EXCHANGE_REQUEST | 거부 |

### 3.6 결제 상태 전이표
| 현재상태 | 이벤트 | 다음상태 | 전이조건 | 부수효과 |
|---|---|---|---|---|
| WAITING | APPROVE | APPROVED | approved_amount = Payment.total_amount | paid_amount 설정, approved_at 설정 |
| WAITING | FAIL | FAILED | PG 실패 응답 | failed_at, failure_reason 설정 |
| APPROVED | COMPLETE | COMPLETED | PG 완료 이벤트 수신 | completed_at 설정 |
| APPROVED | CANCEL | CANCELED | 전액 취소, refunded_amount = 0 | Payment.refunded_amount = paid_amount |
| COMPLETED | PARTIAL_REFUND | PARTIAL_REFUNDED | 환불 후 refunded_amount < paid_amount | refunded_amount 증가 |
| COMPLETED | FULL_REFUND | FULL_REFUNDED | 환불 후 refunded_amount = paid_amount | refunded_amount = paid_amount |
| PARTIAL_REFUNDED | PARTIAL_REFUND | PARTIAL_REFUNDED | 추가 환불 후 refunded_amount < paid_amount | refunded_amount 증가 |
| PARTIAL_REFUNDED | FULL_REFUND | FULL_REFUNDED | 추가 환불 후 refunded_amount = paid_amount | refunded_amount = paid_amount |

### 3.7 결제 불가능 전이
| 현재상태 | 시도 이벤트 | 결과 |
|---|---|---|
| FAILED | APPROVE | 거부 |
| CANCELED | COMPLETE | 거부 |
| FULL_REFUNDED | PARTIAL_REFUND | 거부 |
| WAITING | PARTIAL_REFUND | 거부 |
| APPROVED | FULL_REFUND before CANCEL | 거부, CANCEL만 허용 |

### 3.8 환불 상태 전이표
| 현재상태 | 이벤트 | 다음상태 | 전이조건 | 부수효과 |
|---|---|---|---|---|
| REQUESTED | APPROVE | APPROVED | 판매자 또는 운영자 승인, 또는 배송 전 취소 자동 승인 | approved_at 설정 |
| REQUESTED | REJECT | REJECTED | 판매자 또는 운영자 거부 | failure_reason 저장 |
| REQUESTED | WITHDRAW | CANCELED | 구매자 철회, 승인 전 | 없음 |
| APPROVED | START_PROCESSING | PROCESSING | 반품 수거 시작 또는 취소 무물류 처리 | 없음 |
| PROCESSING | START_PG | PG_PROCESSING | 반품 입고 완료 또는 취소 승인 완료 | PG 환불 요청 |
| PG_PROCESSING | PG_SUCCESS | COMPLETED | PG 환불 성공 이벤트 | Payment.refunded_amount 증가, 결제수단별 refund_amount 증가 |
| PG_PROCESSING | PG_FAIL | FAILED | PG 환불 실패 이벤트 | failure_reason 저장 |
| FAILED | RETRY | PG_PROCESSING | 운영자 또는 시스템 재시도 | 동일 멱등성 키로 PG 재요청 |

### 3.9 환불 불가능 전이
| 현재상태 | 시도 이벤트 | 결과 |
|---|---|---|
| COMPLETED | PG_FAIL | 거부 |
| REJECTED | PG_SUCCESS | 거부 |
| CANCELED | START_PROCESSING | 거부 |
| FAILED | APPROVE | 거부 |
| PROCESSING | WITHDRAW | 거부 |

---

## 4. 비즈니스 규칙

### BR-001 금액 불변식
규칙: Order.total_payment_amount = Order.total_goods_amount + Order.total_shipping_fee  
규칙: Order.total_goods_amount = Σ OrderItem.goods_amount  
규칙: OrderItem.goods_amount = OrderItem.unit_price * OrderItem.quantity  
규칙: Payment.total_amount = Order.total_payment_amount  
규칙: Σ PaymentMethodDetail.amount = Payment.total_amount  
규칙: 주문별 Σ Refund.total_refund_amount <= Payment.paid_amount

정상 케이스: 상품 총액 20,000원, 배송비 3,000원이면 결제 대상 총액 23,000원이다. 결제수단 합계가 23,000원이면 승인을 허용한다.

엣지 케이스 1: 결제수단 합계가 22,999원이면 결제 생성는 400 ERR_AMOUNT_MISMATCH를 반환한다.  
엣지 케이스 2: 이미 refunded_amount가 20,000원인 결제에서 추가 환불 요청 금액이 3,001원이면 부분 환불 실행은 422 ERR_REFUND_EXCEEDS_PAID를 반환한다.

### BR-002 단수 처리
규칙: 모든 금액은 정수 원 단위로 저장한다.  
규칙: 나누어떨어지지 않는 금액은 floor(절사)한다.  
규칙: 주문 단위 할인 안분 시 나머지 잔액은 OrderItem.goods_amount가 가장 큰 상품에 추가한다. goods_amount가 같으면 order_item_id 사전순 첫 항목에 추가한다.  
규칙: 부분 수량 환불의 나머지 잔액은 환불되지 않은 수량에 귀속한다.

정상 케이스: 할인 1,000원을 goods_amount 6,000원, 4,000원 상품에 안분하면 600원, 400원이다.

엣지 케이스 1: 할인 1,000원을 goods_amount 1,000원 상품 3개에 안분하면 floor 333원씩 999원이고 나머지 1원은 order_item_id 사전순 첫 상품에 추가한다.  
엣지 케이스 2: net_goods_amount 999원, quantity 3개 중 1개 환불하면 floor(999 * 1 / 3) = 333원이고 나머지 666원은 미환불 수량에 귀속한다.

### BR-003 재고 예약
규칙: 주문 생성 시 OrderItem.quantity만큼 Stock.available_quantity를 감소하고 Stock.reserved_quantity를 증가한다.  
규칙: 예약 만료 시각은 Order.created_at + 30분이다.  
규칙: Payment.status=WAITING이고 now > stock_reservation_expires_at이면 예약을 해제한다.

정상 케이스: available_quantity 10개에서 2개 주문 생성 시 available_quantity 8개, reserved_quantity 2개가 된다.

엣지 케이스 1: available_quantity 1개에서 2개 주문 생성 시 주문 생성은 409 ERR_STOCK_INSUFFICIENT를 반환한다.  
엣지 케이스 2: 동시 주문으로 version 충돌이 발생하면 3회 재시도하고, 실패 시 409 ERR_STOCK_CONFLICT를 반환한다.

### BR-004 재고 확정 차감과 해제
규칙: Payment.status=APPROVED이면 Stock.reserved_quantity를 감소한다. available_quantity는 이미 감소된 상태를 유지한다.  
규칙: Payment.status=FAILED 또는 CANCELED이면 Stock.reserved_quantity를 감소하고 available_quantity를 증가한다.  
규칙: 주문 취소 완료 시 취소 수량만큼 Stock.reserved_quantity 또는 확정 차감분을 해제하고 available_quantity를 증가한다.  
규칙: 반품 완료 시 반품 수량만큼 Stock.available_quantity를 증가한다.

정상 케이스: 결제 승인 후 reserved_quantity 2개가 0개로 줄고 available_quantity는 8개로 유지된다.

엣지 케이스 1: 결제 실패 후 reserved_quantity 2개를 0개로 만들고 available_quantity를 8개에서 10개로 복원한다.  
엣지 케이스 2: 확정 차감 이후 결제 취소 요청이 들어오면 reserved_quantity가 아닌 확정 차감분을 해제하고 available_quantity를 증가한다.

### BR-005 부분 취소
규칙: 부분 취소는 OrderItem.status가 PAID 또는 PREPARING이고 연결 Shipment.status가 CREATED 또는 PACKING일 때만 허용한다.  
규칙: 부분 수량 취소는 OrderItem.quantity 내에서만 허용한다.  
규칙: 취소 환불 금액은 BR-002 부분 수량 환불 공식을 사용한다.

정상 케이스: 3개 주문상품 중 1개를 배송 준비 전에 취소하면 1개 환불 금액을 계산하고 Refund.type=CANCEL 환불을 생성한다.

엣지 케이스 1: Shipment.status=SHIPPED인 주문상품 취소 요청은 422 ERR_CANCEL_NOT_ALLOWED를 반환한다.  
엣지 케이스 2: 취소 수량이 OrderItem.quantity보다 크면 400 ERR_INVALID_QUANTITY를 반환한다.

### BR-006 부분 환불
규칙: 부분 환불은 RefundItem.quantity 합계가 OrderItem.quantity를 초과할 수 없다.  
규칙: 환불 상품 금액은 floor(OrderItem.net_goods_amount * refund_quantity / OrderItem.quantity)로 계산한다.  
규칙: 전 수량 환불이면 refund_line_amount = OrderItem.net_goods_amount로 계산한다.  
규칙: 환불 총액은 0 미만일 수 없다.

정상 케이스: net_goods_amount 9,000원, quantity 3개 중 1개 반품 시 환불 상품 금액은 3,000원이다.

엣지 케이스 1: net_goods_amount 1,000원, quantity 3개 중 1개 반품 시 floor(1,000 / 3) = 333원이다.  
엣지 케이스 2: 배송비 차감이 환불 상품 금액보다 크면 total_refund_amount는 0원으로 저장한다.

### BR-007 부분 배송
규칙: 한 주문은 판매자별로 Shipment를 분리 생성한다.  
규칙: 동일 판매자라도 분할 출고가 필요하면 ShipmentItem.quantity 합계가 OrderItem.quantity를 넘지 않는 범위에서 여러 Shipment를 생성할 수 있다.  
규칙: 배송 상태는 Shipment 단위로 독립 전이한다.  
규칙: 주문 대표 상태는 RS-001로 계산한다.

정상 케이스: 판매자 A 상품 배송 출발, 판매자 B 상품 준비 중이면 주문 대표 상태는 PARTIAL_SHIPPED이다.

엣지 케이스 1: 판매자 A 배송은 DELIVERED, 판매자 B 배송은 RETURN_REQUESTED이면 주문 대표 상태는 RETURN_REQUESTED이다.  
엣지 케이스 2: OrderItem.quantity 5개 중 3개만 ShipmentItem으로 생성하면 남은 2개는 미배송으로 유지되고 주문 대표 상태는 PARTIAL_SHIPPED이다.

### BR-008 혼합 결제 환불 재분배
규칙: 환불 금액 R에서 coupon_restore_amount를 먼저 계산한다.  
규칙: coupon_restore_amount는 전액 취소이고 Coupon.restorable=true이고 Coupon.expires_at >= now일 때만 PaymentMethodDetail COUPON amount와 같다. 부분 환불에서는 0이다.  
규칙: R_cash = R - coupon_restore_amount  
규칙: point_restore_amount = min(PaymentMethodDetail POINT 잔여 refundable amount, R_cash)  
규칙: R_cash에서 point_restore_amount를 차감한 뒤 bank_refund_amount = min(BANK_TRANSFER 잔여 refundable amount, R_cash)로 계산한다.  
규칙: 남은 R_cash는 card_refund_amount로 계산한다.  
규칙: CARD가 없으면 남은 금액은 BANK_TRANSFER에 배정한다. BANK_TRANSFER도 없으면 POINT에 배정한다.  
규칙: 모든 배정 후 잔여 금액이 0이 아니면 422 ERR_REFUND_ALLOCATION_FAIL을 반환한다.

정상 케이스: 환불 5,000원, POINT 1,000원, CARD 4,000원이면 point_restore_amount 1,000원, card_refund_amount 4,000원이다.

엣지 케이스 1: 환불 500원, POINT 1,000원이면 point_restore_amount 500원, card_refund_amount 0원이다.  
엣지 케이스 2: 전액 취소 R=13,000원, COUPON 2,000원, POINT 1,000원, CARD 10,000원이면 coupon_restore_amount 2,000원, point_restore_amount 1,000원, card_refund_amount 10,000원이다.

### BR-009 쿠폰 할인 안분과 복원
규칙: 쿠폰 할인액은 주문 생성 시 OrderItem.discount_amount로 안분한다.  
규칙: 부분 환불 시 환불 금액에서 OrderItem.discount_amount 중 환불 수량 비례분을 차감한다.  
규칙: 부분 환불에서는 Coupon.status를 RESTORED로 변경하지 않는다.  
규칙: 전액 취소이고 Coupon.restorable=true이고 Coupon.expires_at >= now이면 Coupon.status를 RESTORED로 변경한다.  
규칙: Coupon.expires_at < now이면 Coupon.status를 RESTORED로 변경하지 않고 coupon_restore_amount를 0으로 계산한다.

정상 케이스: discount_amount 2,000원인 주문을 전액 취소하고 쿠폰 만료 전이면 coupon_restore_amount 2,000원, Coupon.status=RESTORED이다.

엣지 케이스 1: discount_amount 2,000원 중 1개 상품만 부분 환불하면 쿠폰은 복원되지 않고 환불 금액에서 비례 할인액이 차감된다.  
엣지 케이스 2: 전액 취소 시점에 Coupon.expires_at이 지났으면 coupon_restore_amount는 0이고 Coupon.status는 USED로 유지된다.

### BR-010 배송비 정책
규칙: Shipment.shipping_fee는 주문 생성 시 shipment.goods_amount >= shipping_policy_threshold이면 0, 아니면 shipping_policy_fee로 계산한다.  
규칙: 부분 환불 또는 부분 취소 후 shipment.goods_amount < shipping_policy_threshold이고 free_shipping_original=true이면 shipping_policy_fee를 deduction_amount에 포함한다.  
규칙: deduction_amount 차감 후 total_refund_amount가 음수이면 0으로 저장한다. 추가 청구는 하지 않는다.  
규칙: 배송 전 전액 취소이고 shipping_fee > 0이면 refund_shipping_fee = shipping_fee로 계산한다.  
규칙: 배송 완료 후 구매자 단순 변심 반품이면 deduction_amount = shipping_policy_fee로 계산한다.  
규칙: 판매자 책임 반품이면 deduction_amount = 0으로 계산한다.

정상 케이스: threshold 50,000원, fee 3,000원, 무료배송 주문에서 20,000원 부분 환불 후 shipment.goods_amount가 40,000원이 되면 deduction_amount 3,000원을 차감한다.

엣지 케이스 1: 환불 상품 금액 2,000원, deduction_amount 3,000원이면 total_refund_amount는 0원이다.  
엣지 케이스 2: 주문 시 shipping_fee 3,000원을 결제했고 배송 전 전액 취소하면 refund_shipping_fee 3,000원을 환불에 포함한다.

### BR-011 취소/반품/교환 구분
규칙: 취소는 Shipment.status가 CREATED 또는 PACKING일 때만 요청할 수 있다.  
규칙: 반품은 Shipment.status=DELIVERED이고 delivered_at + 7일 이내일 때만 요청할 수 있다.  
규칙: 교환은 Shipment.status=DELIVERED이고 delivered_at + 7일 이내이며 교환 대상 option_key의 unit_price가 기존 unit_price와 같을 때만 요청할 수 있다.  
규칙: 교환은 Refund.total_refund_amount를 생성하지 않는다.  
규칙: 교환은 기존 Shipment를 EXCHANGE 흐름으로 전이하고 EXCHANGE_RECEIVED 이후 새 Shipment를 생성한다.

정상 케이스: 배송 완료 3일 차에 반품 요청하면 Refund.type=RETURN, Refund.status=REQUESTED를 생성한다.

엣지 케이스 1: 배송 완료 8일 차 반품 요청은 422 ERR_RETURN_PERIOD_EXPIRED를 반환한다.  
엣지 케이스 2: 교환 대상 상품 단가가 기존 단가와 다르면 422 ERR_EXCHANGE_PRICE_DIFF를 반환한다.

### BR-012 판매자 정산
규칙: 정산 기간은 매월 1일 00:00:00 KST부터 말일 23:59:59 KST까지이다.  
규칙: 정산 지급 예정 시각은 period_end + 7일 00:00:00 KST이다.  
규칙: gross_sales_amount = Σ OrderItem.net_goods_amount 중 구매확정된 수량분이다.  
규칙: shipping_fee_income = Σ Shipment.shipping_fee 중 구매확정 주문의 판매자 배송분이다.  
규칙: commission_amount = floor(gross_sales_amount * commission_rate_bps / 10000)  
규칙: commission_amount 계산의 절사 잔액은 net_amount에 남긴다.  
규칙: net_amount = gross_sales_amount + shipping_fee_income - commission_amount - refund_deduction_amount - hold_amount  
규칙: Refund.status가 REQUESTED, APPROVED, PROCESSING, PG_PROCESSING, FAILED 중 하나이면 해당 금액을 hold_amount에 포함하고 Settlement.status=HOLD로 설정한다.  
규칙: 모든 보류 사유가 종료되면 hold_amount를 0으로 변경하고 Settlement.status=SCHEDULED로 변경한다.  
규칙: 정산 집행 이후 환불이 확정되면 다음 기간 Settlement.refund_deduction_amount에 음수 차감으로 반영한다.

정상 케이스: gross_sales_amount 1,000,000원, commission_rate_bps 500이면 commission_amount = floor(1,000,000 * 500 / 10000) = 50,000원이다.

엣지 케이스 1: gross_sales_amount 999원, commission_rate_bps 333이면 commission_amount = floor(999 * 333 / 10000) = 33원이고 절사 잔액 0.33원 상당은 판매자 net_amount에 남는다.  
엣지 케이스 2: 집행 완료된 정산 기간에서 환불 10,000원이 확정되면 다음 기간 Settlement.refund_deduction_amount에 10,000원을 추가한다.

### BR-013 환불 상한과 결제수단별 캡
규칙: Payment.refunded_amount는 Payment.paid_amount를 초과할 수 없다.  
규칙: PaymentMethodDetail.refund_amount는 해당 PaymentMethodDetail.amount를 초과할 수 없다.  
규칙: 동일 refund_id로 중복 완료 이벤트가 수신되면 최초 1건만 반영한다.  
규칙: 환불 배정 결과 어떤 결제수단에서도 캡 초과가 발생하면 트랜잭션을 중단하고 422 ERR_REFUND_ALLOCATION_FAIL을 반환한다.

정상 케이스: CARD 10,000원 결제에서 4,000원 환불 후 추가 6,000원 환불은 허용되고 Payment.status=FULL_REFUNDED가 된다.

엣지 케이스 1: CARD 10,000원 결제에서 10,001원 환불 요청은 422 ERR_REFUND_EXCEEDS_PAID를 반환한다.  
엣지 케이스 2: 동일 pg_event_id로 REFUND_COMPLETED 웹훅이 2회 수신되면 두 번째는 DUPLICATE_IGNORED로 처리한다.

### BR-014 멱등성 키
규칙: 금액을 변경하는 모든 API는 Idempotency-Key 헤더를 요구한다.  
규칙: Idempotency-Key는 UUID 형식이어야 한다.  
규칙: 서버는 키, 요청 본문 해시, 응답을 24시간 저장한다.  
규칙: 동일 키와 동일 본문 해시 재요청에는 최초 저장된 응답을 반환한다.  
규칙: 동일 키와 다른 본문 해시 재요청에는 409 ERR_IDEMPOTENCY_CONFLICT를 반환한다.  
규칙: 24시간 경과 후 동일 키 재사용은 새로운 요청으로 처리한다.

정상 케이스: 결제 승인 API를 동일 Idempotency-Key로 2회 호출하면 두 번째 호출은 최초 응답을 반환한다.

엣지 케이스 1: 동일 키로 refund_amount를 바꿔 호출하면 409 ERR_IDEMPOTENCY_CONFLICT를 반환한다.  
엣지 케이스 2: 24시간 경과 후 동일 키를 사용하면 새 요청으로 처리한다.

---

## 5. 권한 매트릭스

행은 사용자 유형이다. 셀의 조건부 표시는 하단 조건 ID로 판정한다.

### 5.1 주문/배송/환불 권한
| 사용자 유형 | 주문 생성 | 본인/소속 주문 조회 | 전체 주문 조회 | 주문 취소 | 반품/교환 요청 | 구매확정 | 배송 생성 | 배송 상태 변경 | 환불 승인/거부 | 환불 재시도 |
|---|---|---|---|---|---|---|---|---|---|---|
| 구매자 | 허용 | 조건부 C1 | 거부 | 조건부 C2 | 조건부 C3 | 조건부 C4 | 거부 | 거부 | 거부 | 거부 |
| 판매자 | 거부 | 조건부 C5 | 거부 | 조건부 C6 | 거부 | 거부 | 조건부 C7 | 조건부 C8 | 조건부 C9 | 거부 |
| 운영자 | 거부 | 허용 | 허용 | 조건부 C10 | 거부 | 허용 | 허용 | 허용 | 조건부 C11 | 조건부 C12 |
| 시스템 | 조건부 C13 | 허용 | 허용 | 조건부 C14 | 거부 | 조건부 C15 | 조건부 C16 | 조건부 C17 | 조건부 C18 | 조건부 C19 |

### 5.2 운영/정산/웹훅 권한
| 사용자 유형 | 정산 조회 | 정산 보류/해제 | 적립금 조정 | 재고 조회 | 재고 조정 | 쿠폰 조회 | PG 웹훅 수신 | 거래 대사 조회 |
|---|---|---|---|---|---|---|---|---|
| 구매자 | 거부 | 거부 | 거부 | 거부 | 거부 | 조건부 C20 | 거부 | 거부 |
| 판매자 | 조건부 C21 | 거부 | 거부 | 조건부 C22 | 거부 | 거부 | 거부 | 거부 |
| 운영자 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 거부 | 허용 |
| 시스템 | 조건부 C23 | 조건부 C24 | 조건부 C25 | 허용 | 조건부 C26 | 조건부 C27 | 조건부 C28 | 조건부 C29 |

### 5.3 조건 정의
| 조건 ID | 조건 |
|---|---|
| C1 | buyer_id가 인증된 구매자 본인이어야 한다 |
| C2 | OrderItem.status가 PAID 또는 PREPARING이고 Shipment.status가 CREATED 또는 PACKING이어야 한다 |
| C3 | Shipment.status=DELIVERED이고 now <= delivered_at + 7일이어야 한다 |
| C4 | 모든 OrderItem.status=DELIVERED이어야 한다 |
| C5 | seller_id가 인증된 판매자 본인이고 주문에 해당 판매자 OrderItem이 하나 이상 있어야 한다 |
| C6 | reason_code가 OUT_OF_STOCK 또는 SYSTEM_ERROR이고 Shipment.status가 CREATED 또는 PACKING이어야 한다 |
| C7 | Payment.status가 APPROVED 또는 COMPLETED이고 seller_id가 해당 Shipment.seller_id와 같아야 한다 |
| C8 | seller_id가 해당 Shipment.seller_id와 같고 3.4 배송 상태 전이표를 만족해야 한다 |
| C9 | Refund.status=REQUESTED이고 Refund 관련 OrderItem의 seller_id가 인증 판매자와 같아야 한다 |
| C10 | reason_code가 DEFECT, OUT_OF_STOCK, SYSTEM_ERROR 중 하나여야 한다 |
| C11 | Refund.status가 REQUESTED 또는 REJECTED여야 한다 |
| C12 | Refund.status=FAILED여야 한다 |
| C13 | 배치 JOB-005가 미입금 주문을 취소하는 경우에만 허용한다 |
| C14 | 배송 전 자동 취소 또는 배치 JOB-005인 경우에만 허용한다 |
| C15 | 배치 JOB-004 자동 구매확정인 경우에만 허용한다 |
| C16 | 결제 승인 후 자동 배송 생성 또는 교환 새 배송 생성인 경우에만 허용한다 |
| C17 | PG 배송 완료 동기화 또는 교환 자동 진행인 경우에만 허용한다 |
| C18 | 배송 전 취소 자동 승인 또는 환불 완료 이벤트 처리인 경우에만 허용한다 |
| C19 | Refund.status=FAILED이고 PG 재조회 결과 환불 미완료인 경우에만 허용한다 |
| C20 | owner_id가 인증된 구매자 본인이어야 한다 |
| C21 | seller_id가 인증된 판매자 본인이어야 한다 |
| C22 | product_id가 인증된 판매자 소유 상품이어야 한다 |
| C23 | 배치 JOB-003 정산 집계인 경우에만 허용한다 |
| C24 | Refund, Return, Exchange 보류 사유가 감지된 경우에만 허용한다 |
| C25 | 환불 복원 또는 적립 만료 배치인 경우에만 허용한다 |
| C26 | 주문 생성, 결제 실패, 취소, 반품 완료 이벤트인 경우에만 허용한다 |
| C27 | 환불 완료 시 쿠폰 복원 처리인 경우에만 허용한다 |
| C28 | PG 서명 검증이 성공해야 한다 |
| C29 | 배치 JOB-002 실행인 경우에만 허용한다 |

---

## 6. 화면 정의

### 6.1 구매자 화면
| 화면ID | 화면명 | 접근 권한 | 표시 데이터 | 사용자 액션 | 화면 전이 |
|---|---|---|---|---|---|
| SCR-B-001 | 주문서 작성 | 구매자 | 상품 목록, 쿠폰 목록, 적립금 잔액, 배송지 입력 항목 | 쿠폰 검증, 주문 생성 | SCR-B-002 |
| SCR-B-002 | 결제 | 구매자 C1 | 주문 총액, 결제수단 입력, 결제 상태 | 결제 생성, 결제 상태 새로고침 | SCR-B-003 |
| SCR-B-003 | 주문 목록 | 구매자 C1 | 주문번호, 상태, 총액, 생성 시각 | 주문 선택 | SCR-B-004 |
| SCR-B-004 | 주문 상세 | 구매자 C1 | 주문상품, 배송, 결제, 환불 내역 | 전체 취소, 부분 취소, 반품, 교환, 구매확정 | SCR-B-005 |
| SCR-B-005 | 환불 상세 | 구매자 C1 | 환불 상태, 환불 금액, 결제수단별 환불액 | 목록 복귀 | SCR-B-004 |
| SCR-B-006 | 쿠폰 목록 | 구매자 C20 | 쿠폰 상태, 만료 시각, 할인 값 | 없음 | 없음 |
| SCR-B-007 | 적립금 내역 | 구매자 C1 | 거래 유형, 금액, 잔액 | 없음 | 없음 |

### 6.2 판매자 화면
| 화면ID | 화면명 | 접근 권한 | 표시 데이터 | 사용자 액션 | 화면 전이 |
|---|---|---|---|---|---|
| SCR-S-001 | 판매자 주문 목록 | 판매자 C5 | 주문번호, 구매자 수령인, 상품, 상태 | 주문 선택 | SCR-S-002 |
| SCR-S-002 | 판매자 주문 상세 | 판매자 C5 | 주문상품, 배송, 환불 | 배송 생성, 상태 변경, 운송장 등록, 환불 승인/거부 | SCR-S-003, SCR-S-004 |
| SCR-S-003 | 배송 관리 | 판매자 C5 | 배송 목록, 상태, 운송장 | 상태 변경, 운송장 등록 | SCR-S-002 |
| SCR-S-004 | 환불 관리 | 판매자 C5 | 환불 목록, 상태, 금액 | 승인, 거부 | SCR-S-002 |
| SCR-S-005 | 정산 조회 | 판매자 C21 | 정산 기간, 금액, 상태 | 상세 조회 | 없음 |

### 6.3 운영자 화면
| 화면ID | 화면명 | 접근 권한 | 표시 데이터 | 사용자 액션 | 화면 전이 |
|---|---|---|---|---|---|
| SCR-A-001 | 전체 주문 모니터링 | 운영자 | 주문 목록, 상태, 결제 상태 | 주문 상세 이동, 강제 취소 | SCR-A-002 |
| SCR-A-002 | 환불 처리 | 운영자 | 환불 목록, 상태, 금액 | 승인, 거부, 재시도 | 없음 |
| SCR-A-003 | 정산 관리 | 운영자 | 정산 목록, 보류 금액 | 보류, 해제 | 없음 |
| SCR-A-004 | 재고/적립금 운영 | 운영자 | 재고, 적립금 거래 | 재고 조정, 적립금 조정 | 없음 |
| SCR-A-005 | PG 대사 | 운영자 | 불일치 거래 목록 | 조회 | 없음 |

---

## 7. 배치/스케줄 작업

| 작업명 | 실행 주기 | 처리 내용 | 실패 시 처리 | 재실행 안전성 |
|---|---|---|---|---|
| JOB-001 재고 예약 만료 해제 | 1분 | Order.status=PAYMENT_WAITING이고 stock_reservation_expires_at < now인 주문을 조회하여 재고 예약 해제, Payment.status=CANCELED, Order.status=CANCELED 처리 | 3회 재시도, 실패 건은 dead-letter 테이블에 적재하고 운영자 알림 | order_id 단위 version 잠금과 상태 조건으로 중복 처리 차단 |
| JOB-002 PG 거래 대조 | 10분 | 최근 24시간 Payment, Refund와 PG 조회 결과를 비교하여 금액/상태 불일치를 reconciliation 테이블에 적재 | 체크포인트부터 재시도, 연속 3회 실패 시 운영자 알림 | pg_transaction_id + pg_event_id unique로 중복 적재 차단 |
| JOB-003 정산 집계 | 매일 00:30 KST | 전일 구매확정분을 seller_id별로 집계하여 Settlement 금액 갱신, 월말 최종 집계에서 Settlement 생성 | 1시간 후 재실행, 실패 건은 별도 집계 큐로 이동 | seller_id + period_start unique와 version 잠금으로 재집계 멱등 보장 |
| JOB-004 자동 구매확정 | 매일 01:00 KST | OrderItem.status=DELIVERED이고 delivered_at + 14일 <= now인 항목을 PURCHASE_CONFIRMED로 변경 | 3회 재시도, 실패 항목은 다음 날 재처리 | order_item_id + version 조건으로 중복 확정 차단 |
| JOB-005 미입금 주문 취소 | 5분 | Order.status=PAYMENT_WAITING이고 created_at + 30분 <= now인 주문을 취소하고 재고 해제 | 3회 재시도, 실패 건 dead-letter 적재 | order_id 단위 상태 조건과 version 잠금으로 중복 취소 차단 |
| JOB-006 웹훅 미수신 결제 조회 | 15분 | Payment.status=WAITING이고 created_at + 10분 <= now인 결제를 PG 조회하여 APPROVED, COMPLETED, FAILED로 동기화 | 3회 재시도, PG 조회 실패 시 다음 주기에 재조회 | payment_id + pg_transaction_id 조건과 version 잠금으로 중복 상태 변경 차단 |

---

## 8. 장애 및 정합성 처리

### 8.1 PG 승인은 성공했으나 주문 저장이 실패한 경우
감지 방법: PG 웹훅 수신 또는 JOB-006 PG 조회에서 pg_transaction_id는 존재하지만 Payment 또는 Order가 없는 건을 탐지한다.  
복구 절차:  
1. pg_transaction_id를 unique key로 임시 결제 수신 테이블에 저장한다.  
2. 주문 생성 Idempotency-Key가 존재하면 동일 요청으로 주문 생성을 재실행한다.  
3. Idempotency-Key가 없으면 PG 거래 금액과 동일한 Payment만 WAITING에서 APPROVED로 생성하고, Order가 없으면 자동 전액 취소를 예약한다.  
4. 자동 전액 취소 전 재고 예약이 존재하면 JOB-001이 만료 시각에 재고를 해제한다.  
진실의 원천: PG 승인 기록을 진실의 원천으로 본다. 내부 주문 테이블은 PG 승인 금액과 일치할 때만 확정한다.

### 8.2 웹훅이 중복 수신된 경우
감지 방법: pg_event_id unique 제약으로 중복을 탐지한다.  
복구 절차:  
1. 최초 이벤트는 처리 결과를 idempotency 저장소에 기록한다.  
2. 동일 pg_event_id 재수신은 DUPLICATE_IGNORED를 반환하고 상태를 변경하지 않는다.  
3. 동일 이벤트지만 amount가 다르면 409 ERR_AMOUNT_MISMATCH를 반환하고 reconciliation에 적재한다.  
진실의 원천: 최초 저장된 내부 Payment 상태와 pg_event_id 처리 이력을 진실의 원천으로 본다.

### 8.3 웹훅이 순서가 뒤바뀌어 수신된 경우
감지 방법: event_timestamp와 상태 우선순위로 판정한다. 상태 우선순위는 WAITING < APPROVED < COMPLETED < PARTIAL_REFUNDED < FULL_REFUNDED < FAILED 순이다. FAILED는 최종 실패로 우선한다.  
복구 절차:  
1. 수신 이벤트의 상태 우선순위가 현재 상태보다 낮으면 상태를 변경하지 않는다.  
2. 수신 이벤트의 event_timestamp가 기존 처리 이벤트보다 이전이면 상태를 변경하지 않는다.  
3. 상태 우선순위가 높고 amount 검증이 성공하면 상태를 갱신한다.  
4. 순서 역전으로 인해 환불 완료 전에 환불 실패가 먼저 도착하면 FAILED를 우선 기록하고, 이후 환불 완료 이벤트가 도착하면 PG 재조회로 최종 상태를 확정한 뒤 reconciliation에 적재한다.  
진실의 원천: PG 최종 조회 결과와 상태 우선순위를 진실의 원천으로 본다.

### 8.4 웹훅이 끝까지 오지 않은 경우
감지 방법: JOB-006이 Payment.status=WAITING이고 created_at + 10분 경과한 결제를 PG 조회한다. Refund.status=PG_PROCESSING이고 requested_at + 30분 경과한 환불도 PG 조회한다.  
복구 절차:  
1. PG 조회 결과가 APPROVED 또는 COMPLETED면 Payment 상태를 갱신한다.  
2. PG 조회 결과가 FAILED면 Payment.status=FAILED로 갱신하고 재고 예약을 해제한다.  
3. 환불 조회 결과가 REFUND_COMPLETED면 Refund.status=COMPLETED로 갱신한다.  
4. 환불 조회 결과가 없거나 실패면 Refund.status=FAILED로 변경하고 reconciliation에 적재한다.  
진실의 원천: PG 조회 API 결과를 진실의 원천으로 본다.

### 8.5 재고 차감 후 결제가 실패한 경우
감지 방법: Payment.status=FAILED 또는 JOB-006의 PG 조회 실패 결과로 탐지한다.  
복구 절차:  
1. OrderItem에 연결된 Stock.reserved_quantity를 차감 수량만큼 감소한다.  
2. Stock.available_quantity를 동일 수량만큼 증가한다.  
3. Payment.status=FAILED, Order.status=PAYMENT_WAITING을 유지한다.  
4. stock_reservation_expires_at까지 결제 재승인이 없으면 JOB-005가 주문을 CANCELED로 변경한다.  
진실의 원천: 결제 상태는 PG 조회 결과를 진실의 원천으로 보고, 재고 수량은 Stock.version이 적용된 내부 재고 테이블을 진실의 원천으로 본다.

### 8.6 환불 요청이 PG에서 타임아웃된 경우
감지 방법: Refund.status=PG_PROCESSING이고 requested_at + 30분 경과 건을 JOB-006 또는 운영자 화면에서 탐지한다.  
복구 절차:  
1. 동일 refund_id와 동일 Idempotency-Key로 PG 환불 조회를 실행한다.  
2. PG 환불 완료 확인 시 Refund.status=COMPLETED, Payment.refunded_amount 증가, PaymentMethodDetail.refund_amount 증가를 처리한다.  
3. PG 환불 실패 확인 시 Refund.status=FAILED로 변경하고 환불 재시도로 재시도한다.  
4. PG 상태가 확인되지 않으면 Refund.status를 PG_PROCESSING으로 유지하고 15분 주기로 재조회한다.  
5. 중복 환불 방지를 위해 Payment.refunded_amount와 PaymentMethodDetail.refund_amount 캡 검사를 매 시도마다 실행한다.  
진실의 원천: PG 환불 조회 결과를 진실의 원천으로 본다. 내부 Refund.status는 PG 결과가 확인된 경우에만 COMPLETED로 변경한다.
