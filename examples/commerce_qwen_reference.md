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

## 2. 데이터 모델

금액 컬럼은 모두 정수 원 단위이다. 통화는 KRW로 고정한다. 시각은 UTC ISO 8601 timestamp로 저장한다. 기간 계산은 KST 기준일을 사용한다.

### 2.1 주문 (Order)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| order_id | string | 필수 | PK, UUID | 주문 고유 ID |
| buyer_id | string | 필수 | 길이 1~64 | 구매자 ID |
| order_number | string | 필수 | unique | 조회용 주문 번호 |
| status | enum | 필수 | PAYMENT_WAITING, PAYMENT_COMPLETED, PREPARING, PARTIAL_SHIPPED, ALL_SHIPPED, PARTIAL_DELIVERED, ALL_DELIVERED, PURCHASE_CONFIRMED, CANCEL_REQUESTED, CANCELING, CANCELED, RETURN_REQUESTED, RETURNING, RETURNED, EXCHANGE_REQUESTED, EXCHANGING, EXCHANGED | 주문 대표 상태 |
| total_goods_amount | integer | 필수 | >=0 | 상품 총액 |
| total_shipping_fee | integer | 필수 | >=0 | 배송비 총액 |
| total_payment_amount | integer | 필수 | >=0 | 결제 대상 총액 |
| coupon_id | string | 선택 | FK Coupon | 적용 쿠폰 ID |
| point_used_amount | integer | 필수 | >=0 | 사용 적립금 |
| receiver_name | string | 필수 | 길이 1~100 | 수령인 이름 |
| receiver_phone | string | 필수 | 길이 1~30 | 수령인 연락처 |
| address_line | string | 필수 | 길이 1~300 | 배송 주소 |
| postal_code | string | 필수 | 길이 5~10 | 우편번호 |
| stock_reservation_expires_at | timestamp | 필수 | UTC | 재고 예약 만료 시각 |
| created_at | timestamp | 필수 | UTC | 주문 생성 시각 |
| updated_at | timestamp | 필수 | UTC | 주문 수정 시각 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

### 2.2 주문상품 (OrderItem)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| order_item_id | string | 필수 | PK, UUID | 주문상품 ID |
| order_id | string | 필수 | FK Order | 소속 주문 |
| seller_id | string | 필수 | 길이 1~64 | 판매자 ID |
| product_id | string | 필수 | 길이 1~64 | 상품 ID |
| stock_id | string | 필수 | FK Stock | 재고 ID |
| product_name | string | 필수 | 길이 1~200 | 상품 스냅샷 이름 |
| option_key | string | 필수 | 길이 0~100 | 옵션 식별자 |
| unit_price | integer | 필수 | >=0 | 상품 단가 |
| quantity | integer | 필수 | >=1 | 주문 수량 |
| goods_amount | integer | 필수 | >=0 | unit_price * quantity |
| discount_amount | integer | 필수 | >=0 | 쿠폰 할인 안분액 |
| net_goods_amount | integer | 필수 | >=0 | goods_amount - discount_amount |
| status | enum | 필수 | PAYMENT_WAITING, PAID, CANCELED, PREPARING, SHIPPED, DELIVERED, PURCHASE_CONFIRMED, RETURN_REQUESTED, RETURNING, RETURNED, EXCHANGE_REQUESTED, EXCHANGING, EXCHANGED | 주문상품 상태 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |
| updated_at | timestamp | 필수 | UTC | 수정 시각 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

### 2.3 배송 (Shipment)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| shipment_id | string | 필수 | PK, UUID | 배송 ID |
| order_id | string | 필수 | FK Order | 소속 주문 |
| seller_id | string | 필수 | 길이 1~64 | 판매자 ID |
| status | enum | 필수 | CREATED, PACKING, SHIPPED, DELIVERED, CANCELED, RETURN_REQUESTED, RETURN_PICKUP, RETURN_RECEIVED, RETURN_COMPLETED, EXCHANGE_REQUESTED, EXCHANGE_PICKUP, EXCHANGE_RECEIVED, EXCHANGE_SHIPPED, EXCHANGE_COMPLETED | 배송 상태 |
| shipping_fee | integer | 필수 | >=0 | 실제 부과 배송비 |
| free_shipping_original | boolean | 필수 | true/false | 주문 시점 무료배송 여부 |
| shipping_policy_threshold | integer | 필수 | >=0 | 무료배송 조건 금액 |
| shipping_policy_fee | integer | 필수 | >=0 | 기본 배송비 |
| courier | string | 선택 | 길이 1~100 | 택배사 |
| tracking_number | string | 선택 | 길이 1~100 | 운송장 번호 |
| shipped_at | timestamp | 선택 | UTC | 출고 시각 |
| delivered_at | timestamp | 선택 | UTC | 배송완료 시각 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |
| updated_at | timestamp | 필수 | UTC | 수정 시각 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

### 2.4 배송상품 (ShipmentItem)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| shipment_item_id | string | 필수 | PK, UUID | 배송상품 ID |
| shipment_id | string | 필수 | FK Shipment | 소속 배송 |
| order_item_id | string | 필수 | FK OrderItem | 소속 주문상품 |
| quantity | integer | 필수 | >=1 | 배송 수량 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |

제약: 동일 shipment_id 안에서 동일 order_item_id는 1회만 존재한다.  
제약: order_item_id별 전체 ShipmentItem.quantity 합계는 OrderItem.quantity 이하여야 한다.

### 2.5 결제 (Payment)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| payment_id | string | 필수 | PK, UUID | 결제 ID |
| order_id | string | 필수 | FK Order, unique | 소속 주문 |
| payment_number | string | 필수 | unique | 결제 번호 |
| status | enum | 필수 | WAITING, APPROVED, COMPLETED, FAILED, CANCELED, PARTIAL_REFUNDED, FULL_REFUNDED | 결제 상태 |
| total_amount | integer | 필수 | >=0 | 결제 요청 총액 |
| paid_amount | integer | 필수 | >=0 | 실제 승인 총액 |
| refunded_amount | integer | 필수 | >=0 | 누적 환불 총액 |
| pg_provider | string | 필수 | 길이 1~64 | PG 제공자 식별자 |
| pg_transaction_id | string | 선택 | unique | PG 거래 ID |
| approved_at | timestamp | 선택 | UTC | 승인 시각 |
| completed_at | timestamp | 선택 | UTC | 완료 시각 |
| failed_at | timestamp | 선택 | UTC | 실패 시각 |
| failure_reason | string | 선택 | 길이 1~300 | 실패 사유 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |
| updated_at | timestamp | 필수 | UTC | 수정 시각 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

### 2.6 결제수단내역 (PaymentMethodDetail)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| payment_method_detail_id | string | 필수 | PK, UUID | 결제수단내역 ID |
| payment_id | string | 필수 | FK Payment | 소속 결제 |
| method_type | enum | 필수 | CARD, BANK_TRANSFER, POINT, COUPON | 결제수단 유형 |
| amount | integer | 필수 | >=0 | 수단별 결제 금액 |
| coupon_id | string | 선택 | FK Coupon | 쿠폰 ID |
| point_transaction_id | string | 선택 | FK PointTransaction | 적립금 거래 ID |
| refund_amount | integer | 필수 | >=0 | 수단별 누적 환불 금액 |
| status | enum | 필수 | AUTHORIZED, REFUND_PENDING, REFUNDED, FAILED, CANCELED | 수단 상태 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |
| updated_at | timestamp | 필수 | UTC | 수정 시각 |

제약: PaymentMethodDetail.amount 합계는 Payment.total_amount와 같다.  
제약: PaymentMethodDetail.refund_amount 합계는 Payment.refunded_amount와 같다.  
제약: 각 PaymentMethodDetail.refund_amount는 해당 amount 이하여야 한다.

### 2.7 환불 (Refund)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| refund_id | string | 필수 | PK, UUID | 환불 ID |
| order_id | string | 필수 | FK Order | 소속 주문 |
| payment_id | string | 필수 | FK Payment | 소속 결제 |
| refund_number | string | 필수 | unique | 환불 번호 |
| type | enum | 필수 | CANCEL, RETURN | 환불 유형 |
| status | enum | 필수 | REQUESTED, APPROVED, REJECTED, PROCESSING, PG_PROCESSING, COMPLETED, FAILED, CANCELED | 환불 상태 |
| reason_code | enum | 필수 | BUYER_SIMPLE, DEFECT, WRONG_OPTION, OUT_OF_STOCK, SYSTEM_ERROR | 환불 사유 코드 |
| refund_goods_amount | integer | 필수 | >=0 | 상품 환불 금액 |
| refund_shipping_fee | integer | 필수 | >=0 | 배송비 환불 금액 |
| deduction_amount | integer | 필수 | >=0 | 차감 금액 |
| point_restore_amount | integer | 필수 | >=0 | 적립금 복원 금액 |
| coupon_restore_amount | integer | 필수 | >=0 | 쿠폰 복원 금액 |
| card_refund_amount | integer | 필수 | >=0 | 카드 환불 금액 |
| bank_refund_amount | integer | 필수 | >=0 | 계좌이체 환불 금액 |
| total_refund_amount | integer | 필수 | >=0 | 전체 환불 금액 |
| requested_at | timestamp | 필수 | UTC | 요청 시각 |
| approved_at | timestamp | 선택 | UTC | 승인 시각 |
| completed_at | timestamp | 선택 | UTC | 완료 시각 |
| failure_reason | string | 선택 | 길이 1~300 | 실패 사유 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

제약: total_refund_amount = point_restore_amount + coupon_restore_amount + card_refund_amount + bank_refund_amount  
제약: total_refund_amount = refund_goods_amount + refund_shipping_fee - deduction_amount  
제약: total_refund_amount는 0 이상이어야 한다.

### 2.8 환불상품 (RefundItem)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| refund_item_id | string | 필수 | PK, UUID | 환불상품 ID |
| refund_id | string | 필수 | FK Refund | 소속 환불 |
| order_item_id | string | 필수 | FK OrderItem | 대상 주문상품 |
| quantity | integer | 필수 | >=1 | 환불 수량 |
| refund_unit_amount | integer | 필수 | >=0 | 단위 환불 금액 |
| refund_discount_amount | integer | 필수 | >=0 | 환불 대상 할인 차감액 |
| refund_line_amount | integer | 필수 | >=0 | 라인 환불 금액 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |

제약: refund_line_amount = refund_unit_amount * quantity - refund_discount_amount  
제약: order_item_id별 누적 RefundItem.quantity는 OrderItem.quantity 이하여야 한다.

### 2.9 쿠폰 (Coupon)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| coupon_id | string | 필수 | PK, UUID | 쿠폰 ID |
| owner_id | string | 필수 | 길이 1~64 | 보유자 ID |
| coupon_code | string | 필수 | unique | 쿠폰 코드 |
| status | enum | 필수 | ISSUED, USED, RESTORED, EXPIRED, CANCELED | 쿠폰 상태 |
| discount_type | enum | 필수 | FIXED_AMOUNT, PERCENTAGE | 할인 유형 |
| discount_value | integer | 필수 | >=0 | FIXED_AMOUNT는 원, PERCENTAGE는 permille |
| min_order_amount | integer | 필수 | >=0 | 최소 주문 금액 |
| max_discount_amount | integer | 필수 | >=0 | 최대 할인 금액 |
| restorable | boolean | 필수 | true/false | 환불 시 복원 가능 여부 |
| used_order_id | string | 선택 | 길이 1~64 | 사용 주문 ID 스냅샷 |
| used_at | timestamp | 선택 | UTC | 사용 시각 |
| expires_at | timestamp | 필수 | UTC | 만료 시각 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |
| updated_at | timestamp | 필수 | UTC | 수정 시각 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

### 2.10 적립금거래 (PointTransaction)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| point_transaction_id | string | 필수 | PK, UUID | 적립금 거래 ID |
| user_id | string | 필수 | 길이 1~64 | 사용자 ID |
| order_id | string | 선택 | FK Order | 관련 주문 |
| refund_id | string | 선택 | FK Refund | 관련 환불 |
| type | enum | 필수 | USE, RESTORE, EARN, ADMIN_ADD, ADMIN_SUBTRACT, EXPIRE | 거래 유형 |
| amount | integer | 필수 | >=0 | 거래 금액 |
| balance_after | integer | 필수 | >=0 | 거래 후 잔액 |
| reason_code | enum | 필수 | ORDER_USE, ORDER_RESTORE, ADMIN_ADJUST, EXPIRE, ORDER_EARN | 사유 코드 |
| created_at | timestamp | 필수 | UTC | 생성 시각 |

제약: user_id + order_id + refund_id + type + reason_code 조합은 unique이다. NULL은 빈 문자열로 간주한다.

### 2.11 재고 (Stock)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| stock_id | string | 필수 | PK, UUID | 재고 ID |
| product_id | string | 필수 | 길이 1~64 | 상품 ID |
| option_key | string | 필수 | 길이 0~100 | 옵션 식별자 |
| available_quantity | integer | 필수 | >=0 | 판매 가능 수량 |
| reserved_quantity | integer | 필수 | >=0 | 예약 수량 |
| updated_at | timestamp | 필수 | UTC | 수정 시각 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

제약: product_id + option_key 조합은 unique이다.

### 2.12 정산 (Settlement)
| 필드명 | 타입 | 필수여부 | 제약조건 | 설명 |
|---|---|---|---|---|
| settlement_id | string | 필수 | PK, UUID | 정산 ID |
| seller_id | string | 필수 | 길이 1~64 | 판매자 ID |
| period_start | date | 필수 | KST 기준일 | 정산 기간 시작일 |
| period_end | date | 필수 | KST 기준일 | 정산 기간 종료일 |
| status | enum | 필수 | SCHEDULED, HOLD, EXECUTED, FAILED | 정산 상태 |
| gross_sales_amount | integer | 필수 | >=0 | 확정 판매 총액 |
| shipping_fee_income | integer | 필수 | >=0 | 배송비 수익 |
| commission_amount | integer | 필수 | >=0 | 수수료 |
| refund_deduction_amount | integer | 필수 | >=0 | 환불 차감액 |
| hold_amount | integer | 필수 | >=0 | 보류 금액 |
| net_amount | integer | 필수 | >=0 | 지급 예정액 |
| commission_rate_bps | integer | 필수 | >=0, <=10000 | 수수료율 bps |
| scheduled_at | timestamp | 필수 | UTC | 지급 예정 시각 |
| executed_at | timestamp | 선택 | UTC | 지급 실행 시각 |
| failure_reason | string | 선택 | 길이 1~300 | 실패 사유 |
| version | integer | 필수 | >=1 | 낙관적 잠금 버전 |

제약: seller_id + period_start 조합은 unique이다.  
제약: net_amount = gross_sales_amount + shipping_fee_income - commission_amount - refund_deduction_amount - hold_amount

### 2.13 엔티티 관계 목록
| 관계 | 카디널리티 | FK 방향 | 설명 |
|---|---|---|---|
| Order : OrderItem | 1:N | OrderItem.order_id → Order.order_id | 한 주문은 여러 주문상품을 가진다 |
| Order : Shipment | 1:N | Shipment.order_id → Order.order_id | 한 주문은 판매자별로 여러 배송을 가진다 |
| Order : Payment | 1:1 | Payment.order_id → Order.order_id | 한 주문은 하나의 결제 기록을 가진다 |
| Payment : PaymentMethodDetail | 1:N | PaymentMethodDetail.payment_id → Payment.payment_id | 한 결제는 여러 결제수단으로 구성된다 |
| Payment : Refund | 1:N | Refund.payment_id → Payment.payment_id | 한 결제는 여러 환불을 가질 수 있다 |
| Order : Refund | 1:N | Refund.order_id → Order.order_id | 한 주문은 여러 환불을 가질 수 있다 |
| Refund : RefundItem | 1:N | RefundItem.refund_id → Refund.refund_id | 한 환불은 여러 환불상품을 가진다 |
| OrderItem : RefundItem | 1:N | RefundItem.order_item_id → OrderItem.order_item_id | 한 주문상품은 여러 환불상품에 포함될 수 있다 |
| Shipment : ShipmentItem | 1:N | ShipmentItem.shipment_id → Shipment.shipment_id | 한 배송은 여러 배송상품을 가진다 |
| OrderItem : ShipmentItem | 1:N | ShipmentItem.order_item_id → OrderItem.order_item_id | 한 주문상품은 분할 배송될 수 있다 |
| OrderItem : Stock | N:1 | OrderItem.stock_id → Stock.stock_id | 여러 주문상품이 동일 재고를 참조한다 |
| Order : PointTransaction | 1:N | PointTransaction.order_id → Order.order_id | 한 주문은 여러 적립금 거래를 가질 수 있다 |
| Refund : PointTransaction | 1:N | PointTransaction.refund_id → Refund.refund_id | 한 환불은 여러 적립금 거래를 가질 수 있다 |
| PaymentMethodDetail : PointTransaction | 1:1 | PaymentMethodDetail.point_transaction_id → PointTransaction.point_transaction_id | 적립금 결제수단은 적립금 거래와 연결된다 |
| Coupon : PaymentMethodDetail | 1:N | PaymentMethodDetail.coupon_id → Coupon.coupon_id | 한 쿠폰은 결제수단 내역에서 참조된다 |
| Order : Coupon | N:1 | Order.coupon_id → Coupon.coupon_id | 한 주문은 하나의 쿠폰을 적용할 수 있다 |

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

엣지 케이스 1: 결제수단 합계가 22,999원이면 API-012는 400 ERR_AMOUNT_MISMATCH를 반환한다.  
엣지 케이스 2: 이미 refunded_amount가 20,000원인 결제에서 추가 환불 요청 금액이 3,001원이면 API-016은 422 ERR_REFUND_EXCEEDS_PAID를 반환한다.

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

엣지 케이스 1: available_quantity 1개에서 2개 주문 생성 시 API-001은 409 ERR_STOCK_INSUFFICIENT를 반환한다.  
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

## 6. API 명세

공통 규칙:  
- 금액을 변경하는 API는 Idempotency-Key 헤더를 요구한다.  
- 조회 API는 Idempotency-Key가 필요하지 않다.  
- 모든 요청과 응답 금액은 integer 원 단위이다.  
- 인증 정보는 생략하며, 권한은 5번 권한 매트릭스를 따른다.

### 6.1 주문 API
| ID | 메서드 | 경로 | 설명 | 요청 스키마 | 성공 응답 | 에러 응답 | 필요 권한 | 멱등성 여부 |
|---|---|---|---|---|---|---|---|---|
| API-001 | POST | /v1/orders | 주문 생성 | buyer_id:string; items:array(product_id:string, stock_id:string, quantity:integer, unit_price:integer); coupon_id:string; point_use_amount:integer; receiver_name:string; receiver_phone:string; address_line:string; postal_code:string | 201: order_id:string, order_number:string, status:string, total_goods_amount:integer, total_shipping_fee:integer, total_payment_amount:integer, stock_reservation_expires_at:timestamp | 400 ERR_INVALID_AMOUNT, 404 ERR_STOCK_NOT_FOUND, 409 ERR_STOCK_INSUFFICIENT, 422 ERR_COUPON_INVALID | 구매자 | 예 |
| API-002 | GET | /v1/orders/{order_id} | 주문 상세 조회 | path: order_id:string | 200: order:object, items:array, shipments:array, payment:object | 404 ERR_ORDER_NOT_FOUND | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-003 | GET | /v1/orders | 주문 목록 조회 | query: owner_type:BUYER\|SELLER, owner_id:string, status:string, created_from:timestamp, created_to:timestamp, page:integer, size:integer | 200: orders:array, page:integer, size:integer, total_count:integer | 400 ERR_INVALID_QUERY | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-004 | POST | /v1/orders/{order_id}/cancel | 주문 전체 취소 요청 | path: order_id:string; body: reason_code:enum | 202: refund_id:string, status:string | 404 ERR_ORDER_NOT_FOUND, 409 ERR_INVALID_STATE, 422 ERR_CANCEL_NOT_ALLOWED | 구매자 C2, 판매자 C6, 운영자 C10, 시스템 C14 | 예 |
| API-005 | POST | /v1/orders/{order_id}/return | 주문 전체 반품 요청 | path: order_id:string; body: items:array(order_item_id:string, quantity:integer), reason_code:enum | 202: refund_id:string, status:string | 404, 409, 422 ERR_RETURN_PERIOD_EXPIRED | 구매자 C3, 운영자 | 예 |
| API-006 | POST | /v1/orders/{order_id}/exchange | 주문 전체 교환 요청 | path: order_id:string; body: items:array(order_item_id:string, quantity:integer, target_option_key:string), reason_code:enum | 202: shipment_id:string, status:string | 404, 409, 422 ERR_EXCHANGE_PRICE_DIFF | 구매자 C3 | 예 |
| API-007 | POST | /v1/orders/{order_id}/purchase-confirm | 구매확정 | path: order_id:string; body: order_item_ids:array | 200: order_id:string, status:string | 404, 409 ERR_NOT_DELIVERED | 구매자 C4, 운영자, 시스템 C15 | 예 |
| API-008 | GET | /v1/orders/{order_id}/items | 주문상품 목록 조회 | path: order_id:string | 200: items:array | 404 | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-009 | POST | /v1/orders/{order_id}/items/{order_item_id}/cancel | 주문상품 부분 취소 | path: order_id:string, order_item_id:string; body: quantity:integer, reason_code:enum | 202: refund_id:string, status:string | 400 ERR_INVALID_QUANTITY, 404, 409, 422 ERR_CANCEL_NOT_ALLOWED | 구매자 C2, 판매자 C6, 운영자 C10, 시스템 C14 | 예 |
| API-010 | POST | /v1/orders/{order_id}/items/{order_item_id}/return | 주문상품 부분 반품 | path: order_id:string, order_item_id:string; body: quantity:integer, reason_code:enum | 202: refund_id:string, status:string | 400, 404, 409, 422 ERR_RETURN_PERIOD_EXPIRED | 구매자 C3, 운영자 | 예 |
| API-011 | POST | /v1/orders/{order_id}/items/{order_item_id}/exchange | 주문상품 부분 교환 | path: order_id:string, order_item_id:string; body: quantity:integer, target_option_key:string, reason_code:enum | 202: shipment_id:string, status:string | 400, 404, 409, 422 ERR_EXCHANGE_PRICE_DIFF | 구매자 C3 | 예 |

### 6.2 결제 API
| ID | 메서드 | 경로 | 설명 | 요청 스키마 | 성공 응답 | 에러 응답 | 필요 권한 | 멱등성 여부 |
|---|---|---|---|---|---|---|---|---|
| API-012 | POST | /v1/payments | 결제 생성 | body: order_id:string, pg_provider:string, payment_methods:array(method_type:enum, amount:integer, coupon_id:string, point_use_amount:integer) | 201: payment_id:string, status:string, total_amount:integer | 400 ERR_AMOUNT_MISMATCH, 404, 409 ERR_PAYMENT_EXISTS | 구매자, 시스템 | 예 |
| API-013 | GET | /v1/payments/{payment_id} | 결제 조회 | path: payment_id:string | 200: payment:object, methods:array | 404 | 구매자 C1, 운영자 | 아니오 |
| API-014 | POST | /v1/payments/{payment_id}/approve | 결제 승인 처리 | path: payment_id:string; body: pg_transaction_id:string, approved_amount:integer, approved_at:timestamp | 200: payment_id:string, status:string | 404, 409 ERR_AMOUNT_MISMATCH, 409 ERR_INVALID_STATE | 시스템 | 예 |
| API-015 | POST | /v1/payments/{payment_id}/cancel | 결제 전액 취소 | path: payment_id:string; body: reason_code:enum | 200: refund_id:string, payment_status:string | 404, 409 ERR_INVALID_STATE | 운영자, 시스템 | 예 |
| API-016 | POST | /v1/payments/{payment_id}/partial-refund | 부분 환불 실행 | path: payment_id:string; body: refund_amount:integer, refund_items:array(order_item_id:string, quantity:integer), reason_code:enum, deduction_amount:integer | 201: refund_id:string, status:string, total_refund_amount:integer | 404, 422 ERR_REFUND_EXCEEDS_PAID, 422 ERR_REFUND_ALLOCATION_FAIL | 운영자, 시스템 | 예 |
| API-017 | POST | /v1/pg/webhook | PG 웹훅 수신 | body: pg_event_id:string, pg_transaction_id:string, event_type:enum, amount:integer, event_timestamp:timestamp, pg_status:string | 200: result:RECEIVED\|DUPLICATE_IGNORED | 400 ERR_SIGNATURE_INVALID, 409 ERR_AMOUNT_MISMATCH | 시스템 C28 | 예(pg_event_id) |

### 6.3 환불 API
| ID | 메서드 | 경로 | 설명 | 요청 스키마 | 성공 응답 | 에러 응답 | 필요 권한 | 멱등성 여부 |
|---|---|---|---|---|---|---|---|---|
| API-018 | GET | /v1/refunds/{refund_id} | 환불 상세 조회 | path: refund_id:string | 200: refund:object, items:array | 404 | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-019 | GET | /v1/orders/{order_id}/refunds | 주문 환불 목록 조회 | path: order_id:string | 200: refunds:array | 404 | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-020 | POST | /v1/refunds/{refund_id}/approve | 환불 승인 | path: refund_id:string; body: approver_role:SELLER\|ADMIN, decision_reason:string | 200: refund_id:string, status:string | 404, 409 ERR_INVALID_STATE | 판매자 C9, 운영자 C11 | 예(상태키) |
| API-021 | POST | /v1/refunds/{refund_id}/reject | 환불 거부 | path: refund_id:string; body: approver_role:SELLER\|ADMIN, decision_reason:string | 200: refund_id:string, status:string | 404, 409 | 판매자 C9, 운영자 C11 | 예(상태키) |
| API-022 | POST | /v1/refunds/{refund_id}/retry | 환불 재시도 | path: refund_id:string; body: retry_reason:string | 200: refund_id:string, status:string | 404, 409 ERR_NOT_FAILED | 운영자 C12, 시스템 C19 | 예 |
| API-039 | GET | /v1/seller/refunds | 판매자 환불 목록 조회 | query: seller_id:string, status:string, page:integer, size:integer | 200: refunds:array, page:integer, total_count:integer | 400, 403 | 판매자 C5, 운영자 | 아니오 |
| API-040 | GET | /v1/admin/refunds | 운영자 환불 목록 조회 | query: status:string, type:string, order_id:string, page:integer, size:integer | 200: refunds:array, page:integer, total_count:integer | 400 | 운영자 | 아니오 |

### 6.4 배송 API
| ID | 메서드 | 경로 | 설명 | 요청 스키마 | 성공 응답 | 에러 응답 | 필요 권한 | 멱등성 여부 |
|---|---|---|---|---|---|---|---|---|
| API-023 | GET | /v1/orders/{order_id}/shipments | 주문 배송 목록 조회 | path: order_id:string | 200: shipments:array | 404 | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-024 | POST | /v1/orders/{order_id}/shipments | 배송 생성 | path: order_id:string; body: seller_id:string, items:array(order_item_id:string, quantity:integer), shipping_fee:integer, free_shipping_original:boolean, shipping_policy_threshold:integer, shipping_policy_fee:integer | 201: shipment_id:string, status:string | 400, 404, 409 ERR_SHIPMENT_QUANTITY_EXCEED | 판매자 C7, 운영자 | 예 |
| API-025 | GET | /v1/shipments/{shipment_id} | 배송 상세 조회 | path: shipment_id:string | 200: shipment:object, items:array | 404 | 구매자 C1, 판매자 C5, 운영자 | 아니오 |
| API-026 | PATCH | /v1/shipments/{shipment_id}/status | 배송 상태 변경 | path: shipment_id:string; body: event:enum, reason:string, courier:string, tracking_number:string | 200: shipment_id:string, status:string | 404, 409 ERR_INVALID_TRANSITION | 판매자 C8, 운영자, 시스템 C17 | 예 |
| API-027 | POST | /v1/shipments/{shipment_id}/tracking | 운송장 등록 | path: shipment_id:string; body: courier:string, tracking_number:string | 200: shipment_id:string, courier:string, tracking_number:string | 400, 404 | 판매자 C8, 운영자, 시스템 | 아니오 |

### 6.5 쿠폰/적립금 API
| ID | 메서드 | 경로 | 설명 | 요청 스키마 | 성공 응답 | 에러 응답 | 필요 권한 | 멱등성 여부 |
|---|---|---|---|---|---|---|---|---|
| API-028 | GET | /v1/coupons | 쿠폰 목록 조회 | query: owner_id:string, status:string | 200: coupons:array | 400 | 구매자 C20, 운영자 | 아니오 |
| API-029 | POST | /v1/coupons/validate | 쿠폰 유효성 검증 | body: coupon_id:string, items:array(product_id:string, quantity:integer, unit_price:integer) | 200: valid:boolean, discount_amount:integer, min_order_met:boolean | 404, 422 ERR_COUPON_INVALID | 구매자, 시스템 | 아니오 |
| API-030 | GET | /v1/points/transactions | 적립금 거래 조회 | query: user_id:string, from:timestamp, to:timestamp, page:integer, size:integer | 200: transactions:array, page:integer, total_count:integer | 400 | 구매자 C1, 운영자 | 아니오 |
| API-031 | POST | /v1/points/adjust | 적립금 조정 | body: user_id:string, direction:ADD\|SUBTRACT, amount:integer, reason_code:enum | 201: point_transaction_id:string, balance_after:integer | 400, 422 ERR_POINT_INSUFFICIENT | 운영자, 시스템 C25 | 예 |

### 6.6 재고/정산/대사 API
| ID | 메서드 | 경로 | 설명 | 요청 스키마 | 성공 응답 | 에러 응답 | 필요 권한 | 멱등성 여부 |
|---|---|---|---|---|---|---|---|---|
| API-032 | GET | /v1/stocks/{stock_id} | 재고 조회 | path: stock_id:string | 200: stock:object | 404 | 운영자, 시스템, 판매자 C22 | 아니오 |
| API-033 | POST | /v1/admin/stocks/{stock_id}/adjust | 재고 조정 | path: stock_id:string; body: available_quantity_delta:integer, reason:string | 200: stock:object | 404, 409 ERR_STOCK_NEGATIVE | 운영자, 시스템 C26 | 예 |
| API-034 | GET | /v1/settlements | 정산 목록 조회 | query: seller_id:string, period_start:date, period_end:date, status:string, page:integer, size:integer | 200: settlements:array, page:integer, total_count:integer | 400 | 판매자 C21, 운영자 | 아니오 |
| API-035 | GET | /v1/settlements/{settlement_id} | 정산 상세 조회 | path: settlement_id:string | 200: settlement:object | 404 | 판매자 C21, 운영자 | 아니오 |
| API-036 | POST | /v1/settlements/{settlement_id}/hold | 정산 보류 | path: settlement_id:string; body: hold_amount:integer, reason_code:RETURN_OPEN\|EXCHANGE_OPEN\|FRAUD_REVIEW\|REFUND_IN_PROGRESS | 200: settlement_id:string, status:string | 404, 409 ERR_INVALID_STATE | 운영자, 시스템 C24 | 예 |
| API-037 | POST | /v1/settlements/{settlement_id}/release | 정산 보류 해제 | path: settlement_id:string; body: reason:string | 200: settlement_id:string, status:string | 404, 409 | 운영자, 시스템 C24 | 예 |
| API-038 | GET | /v1/admin/reconciliation/mismatches | 거래 대사 불일치 조회 | query: date:date, status:OPEN\|RESOLVED | 200: mismatches:array | 400 | 운영자 | 아니오 |

---

## 7. 화면 정의

### 7.1 구매자 화면
| 화면ID | 화면명 | 접근 권한 | 표시 데이터 | 사용자 액션 | 호출 API ID | 화면 전이 |
|---|---|---|---|---|---|---|
| SCR-B-001 | 주문서 작성 | 구매자 | 상품 목록, 쿠폰 목록, 적립금 잔액, 배송지 입력 항목 | 쿠폰 검증, 주문 생성 | API-028, API-029, API-001 | SCR-B-002 |
| SCR-B-002 | 결제 | 구매자 C1 | 주문 총액, 결제수단 입력, 결제 상태 | 결제 생성, 결제 상태 새로고침 | API-012, API-013 | SCR-B-003 |
| SCR-B-003 | 주문 목록 | 구매자 C1 | 주문번호, 상태, 총액, 생성 시각 | 주문 선택 | API-003 | SCR-B-004 |
| SCR-B-004 | 주문 상세 | 구매자 C1 | 주문상품, 배송, 결제, 환불 내역 | 전체 취소, 부분 취소, 반품, 교환, 구매확정 | API-002, API-008, API-023, API-019, API-013, API-004, API-009, API-005, API-010, API-006, API-011, API-007 | SCR-B-005 |
| SCR-B-005 | 환불 상세 | 구매자 C1 | 환불 상태, 환불 금액, 결제수단별 환불액 | 목록 복귀 | API-018 | SCR-B-004 |
| SCR-B-006 | 쿠폰 목록 | 구매자 C20 | 쿠폰 상태, 만료 시각, 할인 값 | 없음 | API-028 | 없음 |
| SCR-B-007 | 적립금 내역 | 구매자 C1 | 거래 유형, 금액, 잔액 | 없음 | API-030 | 없음 |

### 7.2 판매자 화면
| 화면ID | 화면명 | 접근 권한 | 표시 데이터 | 사용자 액션 | 호출 API ID | 화면 전이 |
|---|---|---|---|---|---|---|
| SCR-S-001 | 판매자 주문 목록 | 판매자 C5 | 주문번호, 구매자 수령인, 상품, 상태 | 주문 선택 | API-003 | SCR-S-002 |
| SCR-S-002 | 판매자 주문 상세 | 판매자 C5 | 주문상품, 배송, 환불 | 배송 생성, 상태 변경, 운송장 등록, 환불 승인/거부 | API-002, API-008, API-023, API-024, API-026, API-027, API-020, API-021 | SCR-S-003, SCR-S-004 |
| SCR-S-003 | 배송 관리 | 판매자 C5 | 배송 목록, 상태, 운송장 | 상태 변경, 운송장 등록 | API-023, API-025, API-026, API-027 | SCR-S-002 |
| SCR-S-004 | 환불 관리 | 판매자 C5 | 환불 목록, 상태, 금액 | 승인, 거부 | API-039, API-018, API-020, API-021 | SCR-S-002 |
| SCR-S-005 | 정산 조회 | 판매자 C21 | 정산 기간, 금액, 상태 | 상세 조회 | API-034, API-035 | 없음 |

### 7.3 운영자 화면
| 화면ID | 화면명 | 접근 권한 | 표시 데이터 | 사용자 액션 | 호출 API ID | 화면 전이 |
|---|---|---|---|---|---|---|
| SCR-A-001 | 전체 주문 모니터링 | 운영자 | 주문 목록, 상태, 결제 상태 | 주문 상세 이동, 강제 취소 | API-003, API-002, API-004 | SCR-A-002 |
| SCR-A-002 | 환불 처리 | 운영자 | 환불 목록, 상태, 금액 | 승인, 거부, 재시도 | API-040, API-018, API-020, API-021, API-022 | 없음 |
| SCR-A-003 | 정산 관리 | 운영자 | 정산 목록, 보류 금액 | 보류, 해제 | API-034, API-035, API-036, API-037 | 없음 |
| SCR-A-004 | 재고/적립금 운영 | 운영자 | 재고, 적립금 거래 | 재고 조정, 적립금 조정 | API-032, API-033, API-030, API-031 | 없음 |
| SCR-A-005 | PG 대사 | 운영자 | 불일치 거래 목록 | 조회 | API-038 | 없음 |

---

## 8. 배치/스케줄 작업

| 작업명 | 실행 주기 | 처리 내용 | 실패 시 처리 | 재실행 안전성 |
|---|---|---|---|---|
| JOB-001 재고 예약 만료 해제 | 1분 | Order.status=PAYMENT_WAITING이고 stock_reservation_expires_at < now인 주문을 조회하여 재고 예약 해제, Payment.status=CANCELED, Order.status=CANCELED 처리 | 3회 재시도, 실패 건은 dead-letter 테이블에 적재하고 운영자 알림 | order_id 단위 version 잠금과 상태 조건으로 중복 처리 차단 |
| JOB-002 PG 거래 대조 | 10분 | 최근 24시간 Payment, Refund와 PG 조회 결과를 비교하여 금액/상태 불일치를 reconciliation 테이블에 적재 | 체크포인트부터 재시도, 연속 3회 실패 시 운영자 알림 | pg_transaction_id + pg_event_id unique로 중복 적재 차단 |
| JOB-003 정산 집계 | 매일 00:30 KST | 전일 구매확정분을 seller_id별로 집계하여 Settlement 금액 갱신, 월말 최종 집계에서 Settlement 생성 | 1시간 후 재실행, 실패 건은 별도 집계 큐로 이동 | seller_id + period_start unique와 version 잠금으로 재집계 멱등 보장 |
| JOB-004 자동 구매확정 | 매일 01:00 KST | OrderItem.status=DELIVERED이고 delivered_at + 14일 <= now인 항목을 PURCHASE_CONFIRMED로 변경 | 3회 재시도, 실패 항목은 다음 날 재처리 | order_item_id + version 조건으로 중복 확정 차단 |
| JOB-005 미입금 주문 취소 | 5분 | Order.status=PAYMENT_WAITING이고 created_at + 30분 <= now인 주문을 취소하고 재고 해제 | 3회 재시도, 실패 건 dead-letter 적재 | order_id 단위 상태 조건과 version 잠금으로 중복 취소 차단 |
| JOB-006 웹훅 미수신 결제 조회 | 15분 | Payment.status=WAITING이고 created_at + 10분 <= now인 결제를 PG 조회하여 APPROVED, COMPLETED, FAILED로 동기화 | 3회 재시도, PG 조회 실패 시 다음 주기에 재조회 | payment_id + pg_transaction_id 조건과 version 잠금으로 중복 상태 변경 차단 |

---

## 9. 자기 검증

| 점검 항목 | 점검 결과 | 상세 |
|---|---|---|
| 2번 엔티티 필드가 6번 API 스키마와 불일치하는 곳 | 0건 | API-001 성공 응답의 stock_reservation_expires_at는 Order.stock_reservation_expires_at와 일치한다. API-031의 direction + amount는 PointTransaction.type + amount와 매핑된다. API-024의 shipping_policy 필드는 Shipment.shipping_policy_threshold, shipping_policy_fee와 일치한다. |
| 4번 비즈니스 규칙 중 6번 API로 구현 경로가 없는 것 | 3건 | BR-003 재고 예약은 API-001 내부 트랜잭션으로 처리되고 독립된 재고 예약 API는 없다. BR-004 재고 확정/해제는 API-017, JOB-001, JOB-005 내부 처리이며 독립된 재고 확정 API는 없다. BR-009 쿠폰 복원은 API-017 REFUND_COMPLETED 이후 내부 처리이며 독립된 쿠폰 복원 API는 없다. |
| 7번에서 참조한 API ID 중 6번에 없는 것 | 0건 | SCR-S-004가 참조하는 API-039, SCR-A-002가 참조하는 API-040은 6번에 존재한다. |
| 3번 상태 전이 중 트리거할 API가 없는 것 | 3건 | PAYMENT_WAITING → CANCELED 전이는 JOB-005로 처리되고 외부 API가 없다. PAYMENT_WAITING → FAILED 동기화는 JOB-006으로 처리되고 API-017이 없는 경우에 외부 API가 없다. Refund PROCESSING → PG_PROCESSING 전이는 API-020 승인 이후 내부 상태 계산 또는 API-026 반품 입고 이벤트 이후 내부 처리이며 직접 호출 API는 API-016이다. |
| 4번 금액 불변식이 깨질 수 있는 시나리오 | 2건 | 시나리오 1: API-017 웹훅과 API-015 관리자 전액 취소가 동시에 실행될 때 Payment.version 잠금을 생략하면 refunded_amount가 paid_amount를 초과할 수 있다. 본 문서는 Payment.version과 BR-013 캡 검증을 요구한다. 시나리오 2: BR-010에서 deduction_amount가 refund_goods_amount보다 클 때 total_refund_amount를 0으로 clamp하지 않으면 Refund.total_refund_amount 공식이 음수가 된다. 본 문서는 total_refund_amount >=0과 BR-010 clamp 규칙을 요구한다. |

---

## 10. 장애 및 정합성 처리

### 10.1 PG 승인은 성공했으나 주문 저장이 실패한 경우
감지 방법: API-017 웹훅 또는 JOB-006 PG 조회에서 pg_transaction_id는 존재하지만 Payment 또는 Order가 없는 건을 탐지한다.  
복구 절차:  
1. pg_transaction_id를 unique key로 임시 결제 수신 테이블에 저장한다.  
2. API-001 Idempotency-Key가 존재하면 동일 요청으로 주문 생성을 재실행한다.  
3. Idempotency-Key가 없으면 PG 거래 금액과 동일한 Payment만 WAITING에서 APPROVED로 생성하고, Order가 없으면 자동 전액 취소를 예약한다.  
4. 자동 전액 취소 전 재고 예약이 존재하면 JOB-001이 만료 시각에 재고를 해제한다.  
진실의 원천: PG 승인 기록을 진실의 원천으로 본다. 내부 주문 테이블은 PG 승인 금액과 일치할 때만 확정한다.

### 10.2 웹훅이 중복 수신된 경우
감지 방법: pg_event_id unique 제약으로 중복을 탐지한다.  
복구 절차:  
1. 최초 이벤트는 처리 결과를 idempotency 저장소에 기록한다.  
2. 동일 pg_event_id 재수신은 DUPLICATE_IGNORED를 반환하고 상태를 변경하지 않는다.  
3. 동일 이벤트지만 amount가 다르면 409 ERR_AMOUNT_MISMATCH를 반환하고 reconciliation에 적재한다.  
진실의 원천: 최초 저장된 내부 Payment 상태와 pg_event_id 처리 이력을 진실의 원천으로 본다.

### 10.3 웹훅이 순서가 뒤바뀌어 수신된 경우
감지 방법: event_timestamp와 상태 우선순위로 판정한다. 상태 우선순위는 WAITING < APPROVED < COMPLETED < PARTIAL_REFUNDED < FULL_REFUNDED < FAILED 순이다. FAILED는 최종 실패로 우선한다.  
복구 절차:  
1. 수신 이벤트의 상태 우선순위가 현재 상태보다 낮으면 상태를 변경하지 않는다.  
2. 수신 이벤트의 event_timestamp가 기존 처리 이벤트보다 이전이면 상태를 변경하지 않는다.  
3. 상태 우선순위가 높고 amount 검증이 성공하면 상태를 갱신한다.  
4. 순서 역전으로 인해 환불 완료 전에 환불 실패가 먼저 도착하면 FAILED를 우선 기록하고, 이후 환불 완료 이벤트가 도착하면 PG 재조회로 최종 상태를 확정한 뒤 reconciliation에 적재한다.  
진실의 원천: PG 최종 조회 결과와 상태 우선순위를 진실의 원천으로 본다.

### 10.4 웹훅이 끝까지 오지 않은 경우
감지 방법: JOB-006이 Payment.status=WAITING이고 created_at + 10분 경과한 결제를 PG 조회한다. Refund.status=PG_PROCESSING이고 requested_at + 30분 경과한 환불도 PG 조회한다.  
복구 절차:  
1. PG 조회 결과가 APPROVED 또는 COMPLETED면 Payment 상태를 갱신한다.  
2. PG 조회 결과가 FAILED면 Payment.status=FAILED로 갱신하고 재고 예약을 해제한다.  
3. 환불 조회 결과가 REFUND_COMPLETED면 Refund.status=COMPLETED로 갱신한다.  
4. 환불 조회 결과가 없거나 실패면 Refund.status=FAILED로 변경하고 reconciliation에 적재한다.  
진실의 원천: PG 조회 API 결과를 진실의 원천으로 본다.

### 10.5 재고 차감 후 결제가 실패한 경우
감지 방법: Payment.status=FAILED 또는 JOB-006의 PG 조회 실패 결과로 탐지한다.  
복구 절차:  
1. OrderItem에 연결된 Stock.reserved_quantity를 차감 수량만큼 감소한다.  
2. Stock.available_quantity를 동일 수량만큼 증가한다.  
3. Payment.status=FAILED, Order.status=PAYMENT_WAITING을 유지한다.  
4. stock_reservation_expires_at까지 결제 재승인이 없으면 JOB-005가 주문을 CANCELED로 변경한다.  
진실의 원천: 결제 상태는 PG 조회 결과를 진실의 원천으로 보고, 재고 수량은 Stock.version이 적용된 내부 재고 테이블을 진실의 원천으로 본다.

### 10.6 환불 요청이 PG에서 타임아웃된 경우
감지 방법: Refund.status=PG_PROCESSING이고 requested_at + 30분 경과 건을 JOB-006 또는 운영자 화면에서 탐지한다.  
복구 절차:  
1. 동일 refund_id와 동일 Idempotency-Key로 PG 환불 조회를 실행한다.  
2. PG 환불 완료 확인 시 Refund.status=COMPLETED, Payment.refunded_amount 증가, PaymentMethodDetail.refund_amount 증가를 처리한다.  
3. PG 환불 실패 확인 시 Refund.status=FAILED로 변경하고 API-022로 재시도한다.  
4. PG 상태가 확인되지 않으면 Refund.status를 PG_PROCESSING으로 유지하고 15분 주기로 재조회한다.  
5. 중복 환불 방지를 위해 Payment.refunded_amount와 PaymentMethodDetail.refund_amount 캡 검사를 매 시도마다 실행한다.  
진실의 원천: PG 환불 조회 결과를 진실의 원천으로 본다. 내부 Refund.status는 PG 결과가 확인된 경우에만 COMPLETED로 변경한다.
